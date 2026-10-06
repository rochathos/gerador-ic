from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.models.commit import Commit, CommitItem
from app.models.meeting import Meeting
from app.models.catalog_item import CatalogItem
from app.models.execution_history import ExecutionHistory
from app.services.git_service import GitService
from app.services.report_service import ReportService
from app.services.redmine_service import RedmineService
from app.services.meeting_service import MeetingService

router = APIRouter()


def obter_diretorio_templates() -> Path:
    """Retorna o caminho correto para o diretório de templates Jinja2 tanto em dev quanto em executável compilado."""
    import sys
    if hasattr(sys, "_MEIPASS"):
        candidato_meipass = Path(sys._MEIPASS) / "app" / "dashboard" / "templates"
        if candidato_meipass.exists():
            return candidato_meipass
    caminho_local = Path(__file__).resolve().parent / "templates"
    if caminho_local.exists():
        return caminho_local
    from app.core.config import BASE_DIR
    caminho_base = BASE_DIR / "app" / "dashboard" / "templates"
    if caminho_base.exists():
        return caminho_base
    return caminho_local


templates_dir = obter_diretorio_templates()
templates = Jinja2Templates(directory=str(templates_dir))


def _get_default_period():
    """Return default analysis period (e.g. this week or today)."""
    now = datetime.now()
    # Default: beginning of the current week at 08:00 to now
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=8, minute=0, second=0, microsecond=0)
    end_of_period = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if end_of_period < start_of_week:
        end_of_period = now
    return start_of_week, end_of_period


def check_is_commit_saved(c_hash: Optional[str], c_short_hash: Optional[str], saved_hashes: set) -> bool:
    """Check if a commit hash matches any saved CatalogItem commit_hash in the database."""
    if not saved_hashes:
        return False
    candidates = []
    if c_hash:
        candidates.append(c_hash.strip().lower())
    if c_short_hash:
        candidates.append(c_short_hash.strip().lower())

    for cand in candidates:
        if not cand:
            continue
        for sh in saved_hashes:
            if not sh:
                continue
            sh_clean = sh.strip().lower()
            if cand == sh_clean or cand.startswith(sh_clean) or sh_clean.startswith(cand):
                return True
    return False


def enrich_commits_with_saved_items(commits: List[Any], saved_items: List[CatalogItem]) -> None:
    """Enrich commit objects or dictionaries with saved CatalogItem records per nature."""
    saved_map: Dict[str, List[CatalogItem]] = {}
    for si in saved_items:
        if si.commit_hash:
            h = si.commit_hash.strip().lower()
            saved_map.setdefault(h, []).append(si)
            saved_map.setdefault(h[:7], []).append(si)

    for c in commits:
        if isinstance(c, dict):
            c_hash = (c.get("hash") or "").strip().lower()
            c_short = (c.get("short_hash") or c_hash[:7]).strip().lower()
        else:
            c_hash = (getattr(c, "hash", "") or "").strip().lower()
            c_short = (getattr(c, "short_hash", "") or c_hash[:7]).strip().lower()

        raw_items = saved_map.get(c_hash) or saved_map.get(c_short) or []
        items_dict = {i.id: i for i in raw_items}
        items = list(items_dict.values())

        # Prioritize items with non-empty redmine_id
        it_fluxo = (
            next((i for i in items if (i.natureza or "").lower() == "fluxo" and i.redmine_id), None)
            or next((i for i in items if (i.natureza or "").lower() == "fluxo"), None)
        )
        it_sql = (
            next((i for i in items if (i.natureza or "").lower() == "sql" and i.redmine_id), None)
            or next((i for i in items if (i.natureza or "").lower() == "sql"), None)
        )

        if not it_fluxo and items:
            it_fluxo = (
                next((i for i in items if i != it_sql and i.redmine_id), None)
                or next((i for i in items if i != it_sql), None)
                or items[0]
            )

        r_fluxo = it_fluxo.redmine_id if it_fluxo else None
        r_sql = it_sql.redmine_id if it_sql else None

        if not r_fluxo:
            other_with_redmine = next((i for i in items if i != it_sql and i.redmine_id), None)
            if other_with_redmine:
                it_fluxo = other_with_redmine
                r_fluxo = it_fluxo.redmine_id

        is_saved = len(items) > 0
        is_saved_fluxo = (it_fluxo is not None)
        is_saved_sql = (it_sql is not None)

        if isinstance(c, dict):
            c["is_saved"] = is_saved
            c["is_saved_fluxo"] = is_saved_fluxo
            c["is_saved_sql"] = is_saved_sql
            c["redmine_id_fluxo"] = r_fluxo
            c["redmine_id_sql"] = r_sql
            c["redmine_id"] = r_fluxo or r_sql
        else:
            setattr(c, "is_saved", is_saved)
            setattr(c, "is_saved_fluxo", is_saved_fluxo)
            setattr(c, "is_saved_sql", is_saved_sql)
            setattr(c, "redmine_id_fluxo", r_fluxo)
            setattr(c, "redmine_id_sql", r_sql)
            setattr(c, "redmine_id", r_fluxo or r_sql)



@router.get("/", response_class=HTMLResponse)
def home_view(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    repo_path: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    alert_message: Optional[str] = None,
    alert_type: Optional[str] = "info",
    db: Session = Depends(get_db),
):
    """Render main dashboard view.

    If start_date and end_date are provided, queries Git directly in real-time
    without saving to the database.
    """
    start_dt, end_dt = _get_default_period()

    # Query latest execution
    stmt_exec = select(ExecutionHistory).order_by(desc(ExecutionHistory.created_at)).limit(1)
    latest_exec = db.execute(stmt_exec).scalar_one_or_none()

    active_repo = repo_path.strip() if repo_path else settings.DEFAULT_GIT_REPO_PATH
    active_author = author.strip() if author is not None else (settings.GIT_AUTHOR_NAME or "")
    selected_branch = branch.strip() if branch else ""

    commits = []
    is_live_query = False

    active_branch = ""
    local_branches = []
    remote_branches = []
    if Path(active_repo).exists():
        branch_info = GitService.get_branches(active_repo)
        active_branch = branch_info.get("active", "")
        local_branches = branch_info.get("local", [])
        remote_branches = branch_info.get("remote", [])

    # Check if user performed a search/consultation
    if start_date and end_date:
        try:
            s_dt = datetime.fromisoformat(start_date)
            e_dt = datetime.fromisoformat(end_date)
            start_date_val = start_date
            end_date_val = end_date

            is_valid, msg = GitService.validate_repository(active_repo)
            if is_valid:
                raw_commits = GitService.get_commits(
                    repo_path=active_repo,
                    start_date=s_dt,
                    end_date=e_dt,
                    author=active_author if active_author else None,
                    branch=selected_branch if selected_branch else None,
                )
                commits = [CommitItem(c) for c in raw_commits]
                is_live_query = True
                branch_msg = f" na branch '{selected_branch}'" if selected_branch else " em todas as branches"
                alert_message = alert_message or f"Consulta realizada diretamente no Git: {len(commits)} commits encontrados{branch_msg}."
                alert_type = "info"
            else:
                alert_message = msg
                alert_type = "warning"
        except Exception as exc:
            logger.error(f"Erro ao processar consulta de período: {exc}")
            alert_message = f"Erro na consulta: {str(exc)}"
            alert_type = "danger"
            start_date_val = start_dt.strftime("%Y-%m-%dT%H:%M")
            end_date_val = end_dt.strftime("%Y-%m-%dT%H:%M")
    else:
        # Default view
        if latest_exec:
            start_date_val = latest_exec.start_date.strftime("%Y-%m-%dT%H:%M")
            end_date_val = latest_exec.end_date.strftime("%Y-%m-%dT%H:%M")
        else:
            start_date_val = start_dt.strftime("%Y-%m-%dT%H:%M")
            end_date_val = end_dt.strftime("%Y-%m-%dT%H:%M")

        # Query Git directly for author's recent commits in real-time
        if Path(active_repo).exists():
            try:
                raw_commits, _ = GitService.get_commits_paged(
                    repo_path=active_repo,
                    author=active_author if active_author else None,
                    branch=selected_branch if selected_branch else None,
                    skip=0,
                    limit=15,
                )
                commits = [CommitItem(c) for c in raw_commits]
                is_live_query = True
            except Exception as exc:
                logger.warning(f"Erro ao buscar commits recentes do Git para home: {exc}")
                stmt_commits = select(Commit).order_by(desc(Commit.commit_date)).limit(15)
                commits = list(db.execute(stmt_commits).scalars().all())
        else:
            stmt_commits = select(Commit).order_by(desc(Commit.commit_date)).limit(15)
            commits = list(db.execute(stmt_commits).scalars().all())

    # Check saved commits in database
    saved_stmt = select(CatalogItem).where(CatalogItem.commit_hash.is_not(None))
    saved_items = list(db.execute(saved_stmt).scalars().all())
    enrich_commits_with_saved_items(commits, saved_items)

    # Fetch metric totals
    total_commits = len(commits)
    total_meetings = db.execute(select(func.count(Meeting.id))).scalar() or 0
    total_created_ics = (
        db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "criado")).scalar() or 0
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "start_date_val": start_date_val,
            "end_date_val": end_date_val,
            "repo_path_val": active_repo,
            "author_val": active_author,
            "latest_execution": latest_exec,
            "total_commits": total_commits,
            "total_meetings": total_meetings,
            "total_created_ics": total_created_ics,
            "commits": commits,
            "is_live_query": is_live_query,
            "alert_message": alert_message,
            "alert_type": alert_type,
            "author_name": settings.GIT_AUTHOR_NAME,
            "active_branch": active_branch,
            "local_branches": local_branches,
            "remote_branches": remote_branches,
            "selected_branch": selected_branch,
        },
    )


@router.post("/analyze")
def analyze_period(
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
    repo_path: str = Form(...),
    author: Optional[str] = Form(None),
    branch: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Handle period search in real-time without saving commits to DB."""
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except Exception as exc:
        logger.error(f"Formato de data inválido: {exc}")
        return RedirectResponse(
            url="/?alert_message=Formato+de+data+inválido&alert_type=danger",
            status_code=303,
        )

    clean_path = repo_path.strip()
    is_valid, msg = GitService.validate_repository(clean_path)
    if not is_valid:
        logger.warning(f"Validação de repositório falhou: {msg}")
        return RedirectResponse(
            url=f"/?alert_message={msg}&alert_type=warning",
            status_code=303,
        )

    clean_branch = branch.strip() if branch else ""
    author_param = f"&author={quote_plus(author.strip())}" if author else ""
    branch_param = f"&branch={quote_plus(clean_branch)}" if clean_branch else ""
    return RedirectResponse(
        url=f"/?start_date={start_date}&end_date={end_date}&repo_path={clean_path}{author_param}{branch_param}",
        status_code=303,
    )


@router.post("/api/create-ic")
async def create_single_ic(
    request: Request,
    db: Session = Depends(get_db),
):
    """Save or update an individual Catalog Item (1 IC created for a commit)."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
            title = payload.get("title", "")
            description = payload.get("description", "")
            status = payload.get("status", "salvo")
            commit_hash = payload.get("commit_hash", "")
            redmine_id = payload.get("redmine_id", "")
            natureza = payload.get("natureza", "")
            activity_type = payload.get("activity_type", "")
            ic_count = payload.get("ic_count", 1)
        else:
            form_data = await request.form()
            title = form_data.get("title", "")
            description = form_data.get("description", "")
            status = form_data.get("status", "salvo")
            commit_hash = form_data.get("commit_hash", "")
            redmine_id = form_data.get("redmine_id", "")
            natureza = form_data.get("natureza", "")
            activity_type = form_data.get("activity_type", "")
            ic_count = form_data.get("ic_count", 1)

        if not title:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Título do IC é obrigatório."},
            )

        clean_hash = str(commit_hash).strip() if commit_hash else None
        clean_redmine_id = str(redmine_id).strip().lstrip("#") if redmine_id else None
        clean_natureza = str(natureza).strip().lower() if natureza else ""
        if not clean_natureza:
            clean_natureza = "sql" if "banco" in (activity_type or "").lower() else "fluxo"

        # Check if an IC already exists for this commit hash and nature to avoid overwriting different IC types
        existing_item = None
        if clean_hash:
            short_prefix = clean_hash[:7].lower()
            stmt = select(CatalogItem).where(
                (
                    (CatalogItem.commit_hash.ilike(f"{short_prefix}%")) |
                    (CatalogItem.commit_hash == clean_hash)
                ),
                func.lower(CatalogItem.natureza) == clean_natureza,
            ).order_by(desc(CatalogItem.id)).limit(1)
            existing_item = db.execute(stmt).scalar_one_or_none()

        default_act = (
            "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"
            if clean_natureza == "sql"
            else "Desenvolvimento - Criar/Manter tarefa de automação"
        )
        final_activity = str(activity_type).strip() if activity_type else default_act
        final_ic_count = int(ic_count) if str(ic_count).isdigit() else 1

        if existing_item:
            existing_item.title = str(title).strip()
            if description:
                existing_item.description = str(description).strip()
            existing_item.natureza = clean_natureza
            existing_item.activity_type = final_activity
            existing_item.ic_count = final_ic_count
            if clean_redmine_id:
                existing_item.redmine_id = clean_redmine_id
                existing_item.status = "criado"
            elif existing_item.status != "criado":
                existing_item.status = str(status) if status else "salvo"
            item = existing_item
        else:
            final_status = "criado" if clean_redmine_id else (str(status) if status else "salvo")
            item = CatalogItem(
                title=str(title).strip(),
                description=str(description).strip() if description else "",
                status=final_status,
                commit_hash=clean_hash,
                redmine_id=clean_redmine_id,
                natureza=clean_natureza,
                activity_type=final_activity,
                ic_count=final_ic_count,
            )
            db.add(item)

        db.commit()
        db.refresh(item)
        logger.info(f"IC individual #{item.id} salvo ({item.natureza}): status={item.status} hash={item.commit_hash} redmine_id={item.redmine_id} title={item.title[:50]}")
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "natureza": item.natureza,
                "activity_type": item.activity_type,
                "ic_count": item.ic_count,
                "redmine_id": item.redmine_id,
                "message": f"Item de Catálogo ({item.natureza.upper()}) #{item.id} salvo com sucesso no banco de dados com status '{item.status}'!",
            },
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Erro ao salvar IC: {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@router.post("/api/catalog-items/{item_id}/redmine-id")
async def api_update_catalog_item_redmine_id(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Quickly link or update the Redmine issue ID for a saved Catalog Item."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
            redmine_id = payload.get("redmine_id", "")
        else:
            form_data = await request.form()
            redmine_id = form_data.get("redmine_id", "")

        item = db.get(CatalogItem, item_id)
        if not item:
            return JSONResponse(status_code=404, content={"success": False, "message": "Item de Catálogo não encontrado."})

        clean_id = str(redmine_id).strip().lstrip("#") if redmine_id else None
        item.redmine_id = clean_id
        if clean_id:
            item.status = "criado"
        db.commit()
        db.refresh(item)

        return JSONResponse({
            "success": True,
            "id": item.id,
            "redmine_id": item.redmine_id,
            "status": item.status,
            "redmine_url": f"https://redmine.tjce.jus.br/issues/{item.redmine_id}" if item.redmine_id else None,
            "message": f"Número do Redmine #{item.redmine_id} vinculado com sucesso!",
        })
    except Exception as exc:
        db.rollback()
        logger.error(f"Erro ao salvar Redmine ID no IC #{item_id}: {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@router.post("/api/redmine/create-ic")
async def api_create_redmine_ic(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a Catalog Item directly in Redmine via official REST API with step-by-step logging."""
    try:
        body = await request.json()
        title = body.get("title", "").strip()
        description = body.get("description", "").strip()
        commit_hash = body.get("commit_hash", "").strip()
        commit_url = body.get("commit_url", "").strip()
        natureza = body.get("natureza", "").strip().lower()
        ic_count = body.get("ic_count", 1)
        activity_type = body.get("activity_type", "").strip()
        if not activity_type:
            activity_type = (
                "Desenvolvimento - Criar/Manter scripts para extração de dados do banco de dados"
                if natureza == "sql"
                else "Desenvolvimento - Criar/Manter tarefa de automação"
            )
        if not natureza:
            natureza = "sql" if "banco" in activity_type.lower() else "fluxo"
        complexity = body.get("complexity", "Baixa")
        dry_run = bool(body.get("dry_run", False))

        if not title:
            return JSONResponse(status_code=400, content={"success": False, "message": "Título do IC é obrigatório."})

        mode_str = "SIMULAÇÃO" if dry_run else "CRIAÇÃO OFICIAL"
        logger.info(f"[REDMINE API] [{mode_str}] Iniciando processo para IC ({natureza}): '{title[:50]}...' (Commit: {commit_hash})")

        success, issue_url, issue_id, step_logs = RedmineService.create_catalog_item_api(
            title=title,
            description=description,
            commit_hash=commit_hash,
            commit_url=commit_url,
            ic_count=int(ic_count) if str(ic_count).isdigit() else 1,
            activity_type=activity_type,
            complexity=complexity,
            dry_run=dry_run,
        )

        if success and issue_id:
            # Persist or update CatalogItem in PostgreSQL per nature
            item = None
            if commit_hash:
                clean_hash = commit_hash.strip().lower()
                stmt = select(CatalogItem).where(
                    or_(
                        func.lower(CatalogItem.commit_hash) == clean_hash,
                        func.lower(CatalogItem.commit_hash).like(f"{clean_hash}%"),
                    ),
                    func.lower(CatalogItem.natureza) == natureza,
                )
                item = db.execute(stmt).scalars().first()

            final_ic_count = int(ic_count) if str(ic_count).isdigit() else 1
            if not item:
                item = CatalogItem(
                    title=title,
                    description=description,
                    status="criado",
                    redmine_id=str(issue_id),
                    commit_hash=commit_hash or None,
                    natureza=natureza,
                    activity_type=activity_type,
                    ic_count=final_ic_count,
                )
                db.add(item)
            else:
                item.status = "criado"
                item.redmine_id = str(issue_id)
                item.title = title
                item.description = description
                item.natureza = natureza
                item.activity_type = activity_type
                item.ic_count = final_ic_count

            db.commit()
            db.refresh(item)
            logger.info(f"[REDMINE API] Item de Catálogo #{item.id} ({natureza}) vinculado à tarefa Redmine #{issue_id} com sucesso (dry_run={dry_run}).")

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "dry_run": dry_run,
                    "issue_id": issue_id,
                    "issue_url": issue_url,
                    "message": (
                        f"Simulação concluída com sucesso! Tarefa simulada #{issue_id} salva no banco de dados."
                        if dry_run
                        else f"Tarefa #{issue_id} criada com sucesso no Redmine!"
                    ),
                    "logs": step_logs,
                    "catalog_item_id": item.id,
                },
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "dry_run": dry_run,
                    "message": "Falha na validação ou criação da tarefa no Redmine.",
                    "logs": step_logs,
                },
            )
    except Exception as exc:
        logger.error(f"[REDMINE API] Erro inesperado na rota /api/redmine/create-ic: {exc}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(exc), "logs": [str(exc)]},
        )




@router.get("/commits", response_class=HTMLResponse)
def commits_view(
    request: Request,
    repo_name: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    only_xml: Optional[bool] = Query(False),
    db: Session = Depends(get_db),
):
    """Render commits table querying Git directly in real-time with lazy-loading support."""
    active_repo = settings.DEFAULT_REPO_PATH
    author_filter = author.strip() if author and author.strip() else (settings.GIT_AUTHOR_NAME or None)
    clean_branch = branch.strip() if branch else ""

    s_dt = None
    e_dt = None
    if start_date:
        try:
            s_dt = datetime.fromisoformat(start_date)
        except Exception:
            pass
    if end_date:
        try:
            e_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
        except Exception:
            pass

    commits = []
    has_more = False

    active_branch = ""
    local_branches = []
    remote_branches = []

    if Path(active_repo).exists():
        branch_info = GitService.get_branches(active_repo)
        active_branch = branch_info.get("active", "")
        local_branches = branch_info.get("local", [])
        remote_branches = branch_info.get("remote", [])

        try:
            raw_commits, has_more = GitService.get_commits_paged(
                repo_path=active_repo,
                author=author_filter,
                q=q,
                branch=clean_branch if clean_branch else None,
                start_date=s_dt,
                end_date=e_dt,
                only_xml=bool(only_xml),
                skip=0,
                limit=20,
            )
            saved_stmt = select(CatalogItem).where(CatalogItem.commit_hash.is_not(None))
            saved_items = list(db.execute(saved_stmt).scalars().all())

            for c in raw_commits:
                commits.append(CommitItem(c))
            enrich_commits_with_saved_items(commits, saved_items)
        except Exception as exc:
            logger.error(f"Erro ao buscar commits paginados do Git: {exc}")
    else:
        pass

    # XML summary metrics for loaded commits
    xml_commits_count = sum(1 for c in commits if c.has_xml_changes)
    total_xml_files = sum(c.xml_files_count for c in commits)
    total_xml_ins = sum(c.xml_insertions for c in commits)
    total_xml_del = sum(c.xml_deletions for c in commits)
    total_xml_edits = sum(c.xml_total_edits for c in commits)

    available_repos = [settings.DEFAULT_REPO_NAME or "PJE"]

    return templates.TemplateResponse(
        request=request,
        name="commits.html",
        context={
            "active_page": "commits",
            "commits": commits,
            "has_more": has_more,
            "next_skip": len(commits),
            "available_repos": available_repos,
            "selected_repo": repo_name or (settings.DEFAULT_REPO_NAME or "PJE"),
            "filter_start_date": start_date or "",
            "filter_end_date": end_date or "",
            "filter_query": q or "",
            "filter_author": author if author is not None else (settings.GIT_AUTHOR_NAME or ""),
            "selected_branch": clean_branch,
            "active_branch": active_branch,
            "local_branches": local_branches,
            "remote_branches": remote_branches,
            "only_xml": only_xml,
            "xml_commits_count": xml_commits_count,
            "total_xml_files": total_xml_files,
            "total_xml_ins": total_xml_ins,
            "total_xml_del": total_xml_del,
            "total_xml_edits": total_xml_edits,
            "author_name": author_filter or "Todos os Autores",
        },
    )


@router.get("/api/git/branches")
def api_git_branches(
    repo_path: Optional[str] = Query(None),
    refresh: bool = Query(False),
):
    """API endpoint to get list of active, local, and remote branches for autocomplete."""
    active_repo = repo_path.strip() if repo_path and repo_path.strip() else settings.DEFAULT_REPO_PATH
    if not Path(active_repo).exists():
        return JSONResponse({"success": False, "message": "Repositório não encontrado", "active": "", "local": [], "remote": []})

    branch_info = GitService.get_branches(active_repo, force_refresh=refresh)
    return JSONResponse({
        "success": True,
        "active": branch_info.get("active", ""),
        "local": branch_info.get("local", []),
        "remote": branch_info.get("remote", []),
        "total": len(branch_info.get("local", [])) + len(branch_info.get("remote", [])),
    })


@router.get("/api/commits/git-paged")
def api_commits_git_paged(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    only_xml: bool = Query(False),
    db: Session = Depends(get_db),
):
    """API endpoint to lazy-load commits directly from Git."""
    active_repo = settings.DEFAULT_REPO_PATH
    author_filter = author.strip() if author and author.strip() else (settings.GIT_AUTHOR_NAME or None)
    clean_branch = branch.strip() if branch else ""

    s_dt = None
    e_dt = None
    if start_date:
        try:
            s_dt = datetime.fromisoformat(start_date)
        except Exception:
            pass
    if end_date:
        try:
            e_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
        except Exception:
            pass

    try:
        raw_commits, has_more = GitService.get_commits_paged(
            repo_path=active_repo,
            author=author_filter,
            q=q,
            branch=clean_branch if clean_branch else None,
            start_date=s_dt,
            end_date=e_dt,
            only_xml=only_xml,
            skip=skip,
            limit=limit,
        )

        saved_stmt = select(CatalogItem).where(CatalogItem.commit_hash.is_not(None))
        saved_items = list(db.execute(saved_stmt).scalars().all())

        commit_objs = [CommitItem(c) for c in raw_commits]
        enrich_commits_with_saved_items(commit_objs, saved_items)
        commit_items = [ci.to_dict() for ci in commit_objs]

        return JSONResponse({
            "success": True,
            "commits": commit_items,
            "has_more": has_more,
            "next_skip": skip + len(commit_items),
            "count": len(commit_items),
        })
    except Exception as exc:
        logger.error(f"Erro no endpoint /api/commits/git-paged: {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc), "commits": [], "has_more": False})


@router.get("/api/commits/inspect/{commit_hash}")
def api_commits_inspect(
    commit_hash: str,
    db: Session = Depends(get_db),
):
    """API endpoint to inspect any commit by hash in real-time without saving to DB."""
    active_repo = settings.DEFAULT_REPO_PATH
    clean_hash = commit_hash.strip()

    try:
        commit_data = GitService.get_commit_by_hash(active_repo, clean_hash)
        if not commit_data:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Commit '{clean_hash}' não encontrado no repositório local."},
            )

        saved_stmt = select(CatalogItem).where(CatalogItem.commit_hash.is_not(None))
        saved_items = list(db.execute(saved_stmt).scalars().all())

        ci = CommitItem(commit_data)
        enrich_commits_with_saved_items([ci], saved_items)
        c_dict = ci.to_dict()
        c_dict["xml_analyzed"] = True

        return JSONResponse({"success": True, "commit": c_dict})
    except Exception as exc:
        logger.error(f"Erro ao inspecionar commit {clean_hash}: {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@router.get("/meetings", response_class=HTMLResponse)
def meetings_view(request: Request, db: Session = Depends(get_db)):
    """Render meetings list."""
    stmt = select(Meeting).order_by(desc(Meeting.start_time))
    meetings = list(db.execute(stmt).scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="meetings.html",
        context={
            "active_page": "meetings",
            "meetings": meetings,
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.get("/catalog-items", response_class=HTMLResponse)
def catalog_items_view(request: Request, db: Session = Depends(get_db)):
    """Render Catalog Items list."""
    stmt = select(CatalogItem).order_by(desc(CatalogItem.created_at))
    items = list(db.execute(stmt).scalars().all())
    total_saved = db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "salvo")).scalar() or 0
    total_redmine = db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "criado")).scalar() or 0
    total_all = db.execute(select(func.count(CatalogItem.id))).scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "active_page": "catalog_items",
            "catalog_items": items,
            "total_all": total_all,
            "total_saved": total_saved,
            "total_redmine": total_redmine,
            "filter_status": "",
            "filter_q": "",
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.post("/catalog-items/{item_id}/approve")
def approve_catalog_item(item_id: int, db: Session = Depends(get_db)):
    """Approve a Catalog Item."""
    item = db.get(CatalogItem, item_id)
    if item:
        item.status = "aprovado"
        db.commit()
    return RedirectResponse(url="/catalog-items", status_code=303)


@router.post("/catalog-items/{item_id}/delete")
def delete_catalog_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a Catalog Item."""
    item = db.get(CatalogItem, item_id)
    if item:
        db.delete(item)
        db.commit()
    referer = request.headers.get("referer", "/history")
    redirect_url = referer if ("/catalog-items" in referer or "/history" in referer) else "/history"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/history", response_class=HTMLResponse)
def history_view(
    request: Request,
    status_filter: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Render created/saved Catalog Items (ICs) history table."""
    stmt = select(CatalogItem).order_by(desc(CatalogItem.created_at))
    if status_filter:
        stmt = stmt.where(CatalogItem.status == status_filter.strip())
    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            (CatalogItem.title.ilike(search_pattern)) |
            (CatalogItem.commit_hash.ilike(search_pattern)) |
            (CatalogItem.description.ilike(search_pattern))
        )

    items = list(db.execute(stmt).scalars().all())

    total_saved = db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "salvo")).scalar() or 0
    total_redmine = db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "criado")).scalar() or 0
    total_all = db.execute(select(func.count(CatalogItem.id))).scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "active_page": "history",
            "catalog_items": items,
            "total_all": total_all,
            "total_saved": total_saved,
            "total_redmine": total_redmine,
            "filter_status": status_filter or "",
            "filter_q": q or "",
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.get("/export/excel")
def export_excel(execution_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Generate and download Excel report."""
    if execution_id:
        history = db.get(ExecutionHistory, execution_id)
    else:
        history = db.execute(select(ExecutionHistory).order_by(desc(ExecutionHistory.created_at)).limit(1)).scalar_one_or_none()

    if not history:
        # Create a dummy or general history object
        now = datetime.now()
        history = ExecutionHistory(
            start_date=now - timedelta(days=7),
            end_date=now,
            repo_path=settings.DEFAULT_GIT_REPO_PATH,
            status="concluido",
        )

    commits = list(db.execute(select(Commit).order_by(desc(Commit.commit_date))).scalars().all())
    filepath = ReportService.generate_excel(history=history, commits=commits)

    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/export/pdf")
def export_pdf(execution_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Generate and download PDF report."""
    if execution_id:
        history = db.get(ExecutionHistory, execution_id)
    else:
        history = db.execute(select(ExecutionHistory).order_by(desc(ExecutionHistory.created_at)).limit(1)).scalar_one_or_none()

    if not history:
        now = datetime.now()
        history = ExecutionHistory(
            start_date=now - timedelta(days=7),
            end_date=now,
            repo_path=settings.DEFAULT_GIT_REPO_PATH,
            status="concluido",
        )

    commits = list(db.execute(select(Commit).order_by(desc(Commit.commit_date))).scalars().all())
    filepath = ReportService.generate_pdf(history=history, commits=commits)

    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/pdf",
    )


# -----------------------------------------------------------------------------
# Teams & Meetings Routes (Fase 2)
# -----------------------------------------------------------------------------

@router.get("/meetings", response_class=HTMLResponse)
def meetings_view(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Render meetings and Teams ad-hoc calls dashboard."""
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
        except Exception:
            pass

    meetings = MeetingService.get_meetings(db, start_date=start_dt, end_date=end_dt, search=search, status=status)

    total_seconds = sum(MeetingService.parse_duration_to_seconds(m.duration) for m in meetings)
    total_duration_str = MeetingService.format_seconds_to_duration(total_seconds)

    total_meetings = len(meetings)
    total_created = sum(1 for m in meetings if m.is_saved)
    total_pending = total_meetings - total_created

    return templates.TemplateResponse(
        request=request,
        name="meetings.html",
        context={
            "active_page": "meetings",
            "meetings": meetings,
            "total_meetings": total_meetings,
            "total_pending": total_pending,
            "total_created": total_created,
            "total_duration_str": total_duration_str,
            "filter_start_date": start_date or "",
            "filter_end_date": end_date or "",
            "filter_search": search or "",
            "filter_status": status or "",
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.post("/api/meetings/import-teams-calls")
async def api_import_teams_calls(
    request: Request,
    db: Session = Depends(get_db),
):
    """API endpoint to receive calls scraped by Teams Bookmarklet from teams.microsoft.com."""
    try:
        body = await request.json()
        calls = body.get("calls", [])
        if not calls:
            return JSONResponse(status_code=400, content={"success": False, "message": "Nenhuma chamada recebida no payload."})

        created, updated = MeetingService.import_teams_calls(db, calls)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "count": created + updated,
                "created": created,
                "updated": updated,
                "message": f"Sucesso! {created} novas chamadas salvas e {updated} atualizadas.",
            },
        )
    except Exception as exc:
        logger.error(f"[TEAMS IMPORT ERROR] {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@router.post("/api/meetings/create-manual")
async def api_create_meeting_manual(
    request: Request,
    db: Session = Depends(get_db),
):
    """Manually register an ad-hoc call or meeting."""
    try:
        body = await request.json()
        contact = body.get("contact_name", "Colega TJCE").strip()
        call_type = body.get("call_type", "efetuada").strip()
        duration = body.get("duration", "30m").strip()
        date_str = body.get("date_str", "").strip()
        title = body.get("title", f"Alinhamento com {contact}").strip()

        calls = [{
            "contact_name": contact,
            "title": title,
            "call_type": call_type,
            "duration": duration,
            "start_time": date_str,
        }]
        created, updated = MeetingService.import_teams_calls(db, calls)
        return JSONResponse(status_code=200, content={"success": True, "message": "Chamada registrada com sucesso!"})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc)})


@router.post("/api/meetings/simulate-test-calls")
def api_simulate_test_calls(db: Session = Depends(get_db)):
    """Seed 3 realistic sample calls for immediate testing."""
    now = datetime.now()
    sample_calls = [
        {
            "contact_name": "Lucas Oliveira (Dev PJe)",
            "title": "Alinhamento técnico sobre Fluxos e Transições XML",
            "call_type": "efetuada",
            "duration": "35m 10s",
            "start_time": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "contact_name": "Mariana Souza (QA / Testes)",
            "title": "Pareamento para validação de evidência de deploy",
            "call_type": "recebida",
            "duration": "24m 45s",
            "start_time": (now - timedelta(hours=5)).isoformat(),
        },
        {
            "contact_name": "Equipe PJe TJCE",
            "title": "Reunião de alinhamento de sustentação e correções",
            "call_type": "reuniao",
            "duration": "50m 00s",
            "start_time": (now - timedelta(days=1, hours=3)).isoformat(),
        },
    ]
    created, updated = MeetingService.import_teams_calls(db, sample_calls)
    return JSONResponse(status_code=200, content={"success": True, "count": created, "message": f"{created} chamadas de teste geradas com sucesso!"})


@router.post("/api/meetings/create-ic")
async def api_create_meeting_ic(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a Redmine IC for one or multiple meetings/calls."""
    try:
        body = await request.json()
        meeting_ids = body.get("meeting_ids", [])
        title = body.get("title", "Alinhamento técnico de desenvolvimento").strip()
        activity_type = body.get("activity_type", "Gestão - Participação em reunião, exceto reunião de levantamento de requisitos")
        complexity = body.get("complexity", "Baixa")
        dry_run = bool(body.get("dry_run", False))

        if not meeting_ids:
            return JSONResponse(status_code=400, content={"success": False, "message": "Nenhuma reunião selecionada."})

        success, issue_url, issue_id, logs = MeetingService.create_ic_for_meetings(
            db=db,
            meeting_ids=meeting_ids,
            title=title,
            activity_type=activity_type,
            complexity=complexity,
            dry_run=dry_run,
        )

        return JSONResponse(
            status_code=200 if success else 500,
            content={
                "success": success,
                "dry_run": dry_run,
                "issue_id": issue_id,
                "issue_url": issue_url,
                "logs": logs,
                "message": f"Tarefa #{issue_id} criada com sucesso no Redmine!" if success and not dry_run else ("Simulação concluída com 100% de sucesso!" if success else "Falha ao processar tarefa no Redmine."),
            }
        )
    except Exception as exc:
        logger.error(f"[MEETING IC ERROR] {exc}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(exc), "logs": [str(exc)]})


@router.post("/api/meetings/delete")
async def api_delete_meetings(
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete selected meetings or clear all."""
    body = await request.json()
    meeting_ids = body.get("meeting_ids", [])
    if meeting_ids:
        db.query(Meeting).filter(Meeting.id.in_(meeting_ids)).delete(synchronize_session=False)
    else:
        db.query(Meeting).delete()
    db.commit()
    return JSONResponse(status_code=200, content={"success": True, "message": "Chamadas removidas com sucesso."})
