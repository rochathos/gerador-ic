from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.models.commit import Commit
from app.models.meeting import Meeting
from app.models.catalog_item import CatalogItem
from app.models.execution_history import ExecutionHistory
from app.services.git_service import GitService
from app.services.catalog_generator_service import CatalogGeneratorService
from app.services.report_service import ReportService

router = APIRouter()

templates_dir = Path(__file__).parent / "templates"
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


@router.get("/", response_class=HTMLResponse)
def home_view(
    request: Request,
    alert_message: Optional[str] = None,
    alert_type: Optional[str] = "info",
    db: Session = Depends(get_db),
):
    """Render main dashboard view."""
    start_dt, end_dt = _get_default_period()

    # Query latest execution
    stmt_exec = select(ExecutionHistory).order_by(desc(ExecutionHistory.created_at)).limit(1)
    latest_exec = db.execute(stmt_exec).scalar_one_or_none()

    # If there was a previous execution, use its dates by default
    if latest_exec:
        start_date_val = latest_exec.start_date.strftime("%Y-%m-%dT%H:%M")
        end_date_val = latest_exec.end_date.strftime("%Y-%m-%dT%H:%M")
    else:
        start_date_val = start_dt.strftime("%Y-%m-%dT%H:%M")
        end_date_val = end_dt.strftime("%Y-%m-%dT%H:%M")

    repo_path_val = settings.DEFAULT_GIT_REPO_PATH or (latest_exec.repo_path if latest_exec else "")

    # Fetch metric totals
    total_commits = db.execute(select(func.count(Commit.id))).scalar() or 0
    total_meetings = db.execute(select(func.count(Meeting.id))).scalar() or 0
    total_suggested_ics = (
        db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "sugerido")).scalar() or 0
    )
    total_created_ics = (
        db.execute(select(func.count(CatalogItem.id)).where(CatalogItem.status == "criado")).scalar() or 0
    )

    # Fetch recent commits
    stmt_commits = select(Commit).order_by(desc(Commit.commit_date)).limit(15)
    commits = list(db.execute(stmt_commits).scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "home",
            "start_date_val": start_date_val,
            "end_date_val": end_date_val,
            "repo_path_val": repo_path_val,
            "author_val": settings.GIT_AUTHOR_NAME or "",
            "latest_execution": latest_exec,
            "total_commits": total_commits,
            "total_meetings": total_meetings,
            "total_suggested_ics": total_suggested_ics,
            "total_created_ics": total_created_ics,
            "commits": commits,
            "alert_message": alert_message,
            "alert_type": alert_type,
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.post("/analyze")
def analyze_period(
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
    repo_path: str = Form(...),
    author: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Run extraction pipeline for commits in specified period and repo."""
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

    try:
        history, saved_commits = GitService.execute_analysis(
            db=db,
            repo_path=clean_path,
            start_date=start_dt,
            end_date=end_dt,
            author=author.strip() if author else None,
        )

        msg = f"Sucesso! {len(saved_commits)} commits encontrados e persistidos no PostgreSQL (Execução #{history.id})."
        return RedirectResponse(
            url=f"/?alert_message={msg}&alert_type=success",
            status_code=303,
        )

    except Exception as exc:
        logger.error(f"Erro durante execução da análise: {exc}")
        return RedirectResponse(
            url=f"/?alert_message=Erro+ao+executar+análise:+{str(exc)}&alert_type=danger",
            status_code=303,
        )


@router.get("/commits", response_class=HTMLResponse)
def commits_view(
    request: Request,
    repo_name: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    only_xml: Optional[bool] = Query(False),
    db: Session = Depends(get_db),
):
    """Render full commits table with filtering capabilities and XML diff analysis."""
    stmt = select(Commit)

    if repo_name:
        stmt = stmt.where(Commit.repo_name == repo_name)

    if start_date:
        try:
            s_dt = datetime.fromisoformat(start_date)
            stmt = stmt.where(Commit.commit_date >= s_dt)
        except Exception:
            pass

    if end_date:
        try:
            # End of specified day
            e_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
            stmt = stmt.where(Commit.commit_date <= e_dt)
        except Exception:
            pass

    if q:
        query_pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Commit.message.ilike(query_pattern),
                Commit.author.ilike(query_pattern),
                Commit.hash.ilike(query_pattern),
            )
        )

    stmt = stmt.order_by(desc(Commit.commit_date))
    commits = list(db.execute(stmt).scalars().all())

    # Calculate global XML stats before filtering if only_xml is toggled
    xml_commits_count = sum(1 for c in commits if c.has_xml_changes)
    total_xml_files = sum(c.xml_files_count for c in commits)
    total_xml_ins = sum(c.xml_insertions for c in commits)
    total_xml_del = sum(c.xml_deletions for c in commits)
    total_xml_edits = sum(c.xml_total_edits for c in commits)

    if only_xml:
        commits = [c for c in commits if c.has_xml_changes]

    # Get list of distinct repository names
    repo_stmt = select(Commit.repo_name).distinct().where(Commit.repo_name.is_not(None))
    available_repos = [r for r in db.execute(repo_stmt).scalars().all() if r]

    return templates.TemplateResponse(
        request=request,
        name="commits.html",
        context={
            "active_page": "commits",
            "commits": commits,
            "available_repos": available_repos,
            "selected_repo": repo_name or "",
            "filter_start_date": start_date or "",
            "filter_end_date": end_date or "",
            "filter_query": q or "",
            "only_xml": only_xml,
            "xml_commits_count": xml_commits_count,
            "total_xml_files": total_xml_files,
            "total_xml_ins": total_xml_ins,
            "total_xml_del": total_xml_del,
            "total_xml_edits": total_xml_edits,
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


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

    return templates.TemplateResponse(
        request=request,
        name="catalog_items.html",
        context={
            "active_page": "catalog_items",
            "catalog_items": items,
            "author_name": settings.GIT_AUTHOR_NAME,
        },
    )


@router.post("/generate-ics")
def generate_ics(db: Session = Depends(get_db)):
    """Generate Catalog Item suggestions from commits in DB."""
    commits = list(db.execute(select(Commit).order_by(desc(Commit.commit_date)).limit(50)).scalars().all())
    if not commits:
        return RedirectResponse(
            url="/catalog-items?alert_message=Nenhum+commit+encontrado+para+gerar+sugestões&alert_type=warning",
            status_code=303,
        )

    suggestions = CatalogGeneratorService.generate_suggestions(commits=commits)
    CatalogGeneratorService.save_suggestions(db=db, suggestions=suggestions)

    return RedirectResponse(
        url="/catalog-items?alert_message=Sugestões+de+IC+geradas+com+sucesso!&alert_type=success",
        status_code=303,
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
def delete_catalog_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a Catalog Item."""
    item = db.get(CatalogItem, item_id)
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/catalog-items", status_code=303)


@router.get("/history", response_class=HTMLResponse)
def history_view(request: Request, db: Session = Depends(get_db)):
    """Render execution history table."""
    stmt = select(ExecutionHistory).order_by(desc(ExecutionHistory.created_at))
    executions = list(db.execute(stmt).scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "active_page": "history",
            "executions": executions,
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
