from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re
import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.logger import logger
from app.models.commit import Commit
from app.models.execution_history import ExecutionHistory


class GitService:
    """Service to interact with local Git repositories using GitPython."""

    EXCLUDED_XML_TAGS = {
        "end-state",
        "process-definition",
        "start-state",
        "assignment",
        "controller",
        "task",
        "script",
        "event",
    }
    TAG_REGEX = re.compile(r"<([a-zA-Z_:][a-zA-Z0-9_.:-]*)")
    DIFF_GIT_REGEX = re.compile(r'diff --git (?:\"a/|a/)(.*) (?:\"b/|b/)(.*)')

    @classmethod
    def analyze_commit_xml_tags(cls, repo: git.Repo, commit_hash: str) -> Dict[str, Any]:
        """Extract XML tag metrics (both added and removed) globally and per flow from commit diff."""
        added_tags: Dict[str, int] = {}
        removed_tags: Dict[str, int] = {}
        flows: Dict[str, Dict[str, Any]] = {}
        current_flow: Optional[str] = None

        try:
            patch_output = repo.git.show(commit_hash, "--pretty=format:", "-p", "--", "*.xml")
            if patch_output:
                for line in patch_output.splitlines():
                    if line.startswith("diff --git "):
                        m = cls.DIFF_GIT_REGEX.match(line)
                        if m:
                            raw_target = m.group(2).rstrip('"')
                            current_flow = cls.decode_git_path(raw_target)
                        else:
                            current_flow = "arquivo.xml"
                        if current_flow not in flows:
                            flows[current_flow] = {
                                "flow_name": current_flow.split("/")[-1].split("\\")[-1],
                                "path": current_flow,
                                "added": {},
                                "removed": {},
                                "total_added": 0,
                                "total_removed": 0,
                                "total_ics": 0,
                            }
                        continue

                    if line.startswith("+") and not line.startswith("+++"):
                        match = cls.TAG_REGEX.search(line)
                        if match:
                            tag = match.group(1).lower()
                            if tag not in cls.EXCLUDED_XML_TAGS:
                                added_tags[tag] = added_tags.get(tag, 0) + 1
                                if current_flow:
                                    flow_dict = flows[current_flow]
                                    flow_dict["added"][tag] = flow_dict["added"].get(tag, 0) + 1
                                    flow_dict["total_added"] += 1
                                    flow_dict["total_ics"] += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        match = cls.TAG_REGEX.search(line)
                        if match:
                            tag = match.group(1).lower()
                            if tag not in cls.EXCLUDED_XML_TAGS:
                                removed_tags[tag] = removed_tags.get(tag, 0) + 1
                                if current_flow:
                                    flow_dict = flows[current_flow]
                                    flow_dict["removed"][tag] = flow_dict["removed"].get(tag, 0) + 1
                                    flow_dict["total_removed"] += 1
                                    flow_dict["total_ics"] += 1
        except Exception as exc:
            logger.debug(f"Erro ao extrair diff de tags XML para o commit {commit_hash[:7]}: {exc}")

        # Keep flows that had at least one tag change
        active_flows = {k: v for k, v in flows.items() if v["total_ics"] > 0}

        total_added = sum(added_tags.values())
        total_removed = sum(removed_tags.values())
        total_ics = total_added + total_removed
        return {
            "added": added_tags,
            "removed": removed_tags,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_ics": total_ics,
            "flows": active_flows,
        }

    @staticmethod
    def decode_git_path(path: str) -> str:
        """Decode Git quoted paths containing octal escape sequences (e.g. \\303\\255 -> í)."""
        if not path:
            return ""
        clean = str(path).strip("\"'")
        if "\\" in clean:
            try:
                return clean.encode("latin1").decode("unicode_escape").encode("latin1").decode("utf-8")
            except Exception:
                return clean
        return clean

    @staticmethod
    def validate_repository(repo_path: str | Path) -> Tuple[bool, str]:
        """Validate if the given path is a valid Git repository."""
        path = Path(repo_path).resolve()
        if not path.exists():
            return False, f"Caminho não encontrado: {path}"
        if not path.is_dir():
            return False, f"Caminho não é um diretório: {path}"

        try:
            repo = git.Repo(path)
            # Ensure it's not a bare repository with no head
            if repo.bare and not list(repo.heads):
                return False, "Repositório Git está vazio (bare/sem branches)."
            return True, f"Repositório válido: {path.name}"
        except InvalidGitRepositoryError:
            return False, f"O diretório não é um repositório Git válido: {path}"
        except NoSuchPathError:
            return False, f"Caminho inexistente: {path}"
        except Exception as exc:
            return False, f"Erro ao acessar repositório: {str(exc)}"

    @staticmethod
    def get_repo_name(repo_path: str | Path) -> str:
        """Extract a friendly repository name."""
        path = Path(repo_path).resolve()
        try:
            repo = git.Repo(path)
            for remote in repo.remotes:
                for url in remote.urls:
                    name = url.rstrip("/").split("/")[-1]
                    if name.endswith(".git"):
                        name = name[:-4]
                    if name:
                        return name
        except Exception:
            pass
        return path.name

    @classmethod
    def get_commit_url(cls, repo_path: str | Path, commit_hash: str) -> Optional[str]:
        """Generate web URL for viewing the commit on GitHub, GitLab, etc."""
        path = Path(repo_path).resolve()
        try:
            repo = git.Repo(path)
            for remote in repo.remotes:
                for raw_url in remote.urls:
                    url = raw_url.strip()
                    # Convert SSH syntax: git@domain:org/repo.git -> https://domain/org/repo
                    if url.startswith("git@"):
                        url = url.replace(":", "/", 1).replace("git@", "https://")
                    if url.endswith(".git"):
                        url = url[:-4]
                    url = url.rstrip("/")

                    # Detect platform URL structure
                    url_lower = url.lower()
                    if "gitlab" in url_lower or "git.tjce" in url_lower or "git.cnj" in url_lower:
                        return f"{url}/-/commit/{commit_hash}"
                    elif "bitbucket" in url_lower:
                        return f"{url}/commits/{commit_hash}"
                    elif "dev.azure.com" in url_lower or "visualstudio.com" in url_lower:
                        return f"{url}/commit/{commit_hash}"
                    else:
                        # Default standard (GitHub, Gitea, etc.)
                        return f"{url}/commit/{commit_hash}"
        except Exception:
            pass
        return None


    @classmethod
    def get_commits(
        cls,
        repo_path: str | Path,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        author: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch commits in the specified period, optionally filtered by author."""
        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            logger.error(f"Validação de repositório falhou: {msg}")
            raise ValueError(msg)

        logger.info(
            f"Buscando commits no repositório '{path}' entre {start_date} e {end_date} (autor: {author or 'TODOS'})"
        )

        repo = git.Repo(path)

        start_date_tz = None
        if start_date is not None:
            start_date_tz = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date

        end_date_tz = None
        if end_date is not None:
            end_date_tz = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date

        commits_found: List[Dict[str, Any]] = []

        try:
            # We iterate through all branches/commits
            # Passing --all ensures commits on any branch are retrieved
            iter_kwargs: Dict[str, Any] = {
                "all": True,
            }
            if start_date_tz is not None:
                iter_kwargs["since"] = int(start_date_tz.timestamp())
            if end_date_tz is not None:
                iter_kwargs["until"] = int(end_date_tz.timestamp())

            for commit in repo.iter_commits(**iter_kwargs):
                commit_dt = commit.committed_datetime

                # Safety check against time boundaries
                if start_date_tz is not None and commit_dt < start_date_tz:
                    continue
                if end_date_tz is not None and commit_dt > end_date_tz:
                    continue

                # Filter by author if provided
                if author:
                    author_query = author.strip().lower()
                    author_name = (commit.author.name or "").lower()
                    author_email = (commit.author.email or "").lower()
                    if author_query not in author_name and author_query not in author_email:
                        continue

                # Get changed files with diff metrics (insertions, deletions, lines)
                files_changed: List[Dict[str, Any]] = []
                try:
                    stats = commit.stats
                    for file_path, file_stat in stats.files.items():
                        clean_path = cls.decode_git_path(file_path)
                        is_xml = clean_path.lower().endswith(".xml")
                        files_changed.append({
                            "path": clean_path,
                            "filename": clean_path.replace("\\", "/").split("/")[-1],
                            "is_xml": is_xml,
                            "insertions": file_stat.get("insertions", 0),
                            "deletions": file_stat.get("deletions", 0),
                            "lines": file_stat.get("lines", 0),
                        })
                except Exception as stat_err:
                    logger.debug(f"Não foi possível obter stats do commit {commit.hexsha[:7]}: {stat_err}")
                    try:
                        if commit.parents:
                            diff = commit.diff(commit.parents[0])
                            for d in diff:
                                target_path = d.a_path or d.b_path
                                if target_path:
                                    clean_path = cls.decode_git_path(target_path)
                                    files_changed.append({
                                        "path": clean_path,
                                        "filename": clean_path.replace("\\", "/").split("/")[-1],
                                        "is_xml": clean_path.lower().endswith(".xml"),
                                        "insertions": 0,
                                        "deletions": 0,
                                        "lines": 0,
                                    })
                    except Exception:
                        files_changed = []

                # Check for XML changes and analyze tags using icf.sh rules
                has_xml = any(
                    f.get("is_xml") or cls.decode_git_path(str(f.get("path", ""))).lower().endswith(".xml")
                    for f in files_changed
                    if isinstance(f, dict)
                )
                xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if has_xml else {
                    "added": {},
                    "removed": {},
                    "total_added": 0,
                    "total_removed": 0,
                    "total_ics": 0,
                    "flows": {},
                }

                commit_author_display = f"{commit.author.name} <{commit.author.email}>" if commit.author.email else commit.author.name
                commit_url = cls.get_commit_url(path, commit.hexsha)

                commits_found.append(
                    {
                        "hash": commit.hexsha,
                        "author": commit_author_display,
                        "author_name": commit.author.name or "",
                        "author_email": commit.author.email or "",
                        "commit_date": commit_dt,
                        "message": commit.message.strip(),
                        "files_changed": files_changed,
                        "repo_name": cls.get_repo_name(path),
                        "repo_path": str(path),
                        "commit_url": commit_url,
                        "xml_tags_metrics": xml_analysis,
                        "ic_count": xml_analysis["total_ics"],
                    }
                )

            # Sort chronologically (oldest to newest)
            commits_found.sort(key=lambda c: c["commit_date"])
            logger.info(f"Busca finalizada: {len(commits_found)} commits encontrados.")
            return commits_found

        except Exception as exc:
            logger.error(f"Erro ao buscar commits no Git: {exc}")
            raise

    @classmethod
    def get_commit_by_hash(cls, repo_path: str | Path, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Look up a single commit directly from Git repository by full or abbreviated hash."""
        path = Path(repo_path).resolve()
        is_valid, _ = cls.validate_repository(path)
        if not is_valid:
            return None
        try:
            repo = git.Repo(path)
            c = repo.commit(commit_hash.strip())
            files_changed: List[Dict[str, Any]] = []
            try:
                for file_path, file_stat in c.stats.files.items():
                    clean_path = cls.decode_git_path(file_path)
                    files_changed.append({
                        "path": clean_path,
                        "filename": clean_path.replace("\\", "/").split("/")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "insertions": file_stat.get("insertions", 0),
                        "deletions": file_stat.get("deletions", 0),
                        "lines": file_stat.get("lines", 0),
                    })
            except Exception:
                files_changed = []

            has_xml = any(f.get("is_xml") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, c.hexsha) if has_xml else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            author_display = f"{c.author.name} <{c.author.email}>" if c.author.email else c.author.name
            return {
                "hash": c.hexsha,
                "author": author_display,
                "author_name": c.author.name or "",
                "author_email": c.author.email or "",
                "commit_date": c.committed_datetime,
                "message": c.message.strip(),
                "files_changed": files_changed,
                "repo_name": cls.get_repo_name(path),
                "repo_path": str(path),
                "commit_url": cls.get_commit_url(path, c.hexsha),
                "xml_tags_metrics": xml_analysis,
                "ic_count": xml_analysis["total_ics"],
            }
        except Exception as exc:
            logger.debug(f"Commit {commit_hash} não encontrado diretamente no Git: {exc}")
            return None

    @classmethod
    def get_commits_paged(
        cls,
        repo_path: str | Path,
        author: Optional[str] = None,
        q: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        only_xml: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch a page of commits directly from Git with lazy-loading support without saving to database."""
        path = Path(repo_path).resolve()
        is_valid, msg = cls.validate_repository(path)
        if not is_valid:
            logger.error(f"Validação de repositório falhou: {msg}")
            raise ValueError(msg)

        repo = git.Repo(path)

        # 1. Direct hash lookup if q is provided and matches a commit
        if q and len(q.strip()) >= 4:
            clean_q = q.strip()
            single_commit = cls.get_commit_by_hash(path, clean_q)
            if single_commit:
                if only_xml and not any(f.get("is_xml") for f in single_commit.get("files_changed", [])):
                    return [], False
                return [single_commit], False

        # 2. Iterate commits directly from Git
        iter_kwargs: Dict[str, Any] = {"all": True}
        start_date_tz = None
        if start_date is not None:
            start_date_tz = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
            iter_kwargs["since"] = int(start_date_tz.timestamp())

        end_date_tz = None
        if end_date is not None:
            end_date_tz = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
            iter_kwargs["until"] = int(end_date_tz.timestamp())

        if author:
            iter_kwargs["author"] = author.strip()

        matched_commits: List[Dict[str, Any]] = []
        has_more = False
        skipped = 0
        query_text = q.strip().lower() if q else ""

        for commit in repo.iter_commits(**iter_kwargs):
            commit_dt = commit.committed_datetime
            if start_date_tz is not None and commit_dt < start_date_tz:
                continue
            if end_date_tz is not None and commit_dt > end_date_tz:
                continue

            msg = commit.message.strip()
            c_author_name = commit.author.name or ""
            c_author_email = commit.author.email or ""

            if query_text:
                if (
                    query_text not in commit.hexsha.lower()
                    and query_text not in msg.lower()
                    and query_text not in c_author_name.lower()
                    and query_text not in c_author_email.lower()
                ):
                    continue

            files_changed: List[Dict[str, Any]] = []
            try:
                for file_path, file_stat in commit.stats.files.items():
                    clean_path = cls.decode_git_path(file_path)
                    files_changed.append({
                        "path": clean_path,
                        "filename": clean_path.replace("\\", "/").split("/")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "insertions": file_stat.get("insertions", 0),
                        "deletions": file_stat.get("deletions", 0),
                        "lines": file_stat.get("lines", 0),
                    })
            except Exception:
                files_changed = []

            if only_xml and not any(f.get("is_xml") for f in files_changed):
                continue

            if skipped < skip:
                skipped += 1
                continue

            if len(matched_commits) >= limit:
                has_more = True
                break

            has_xml = any(f.get("is_xml") for f in files_changed)
            xml_analysis = cls.analyze_commit_xml_tags(repo, commit.hexsha) if has_xml else {
                "added": {},
                "removed": {},
                "total_added": 0,
                "total_removed": 0,
                "total_ics": 0,
                "flows": {},
            }
            author_display = f"{c_author_name} <{c_author_email}>" if c_author_email else c_author_name

            matched_commits.append({
                "hash": commit.hexsha,
                "author": author_display,
                "author_name": c_author_name,
                "author_email": c_author_email,
                "commit_date": commit_dt,
                "message": msg,
                "files_changed": files_changed,
                "repo_name": cls.get_repo_name(path),
                "repo_path": str(path),
                "commit_url": cls.get_commit_url(path, commit.hexsha),
                "xml_tags_metrics": xml_analysis,
                "ic_count": xml_analysis["total_ics"],
            })

        return matched_commits, has_more

    @classmethod
    def save_commits(
        cls,
        db: Session,
        commits_data: List[Dict[str, Any]],
        execution_id: Optional[int] = None,
    ) -> List[Commit]:
        """Persist retrieved commits into the PostgreSQL database."""
        saved_records: List[Commit] = []
        try:
            for item in commits_data:
                # Check if commit hash already exists
                stmt = select(Commit).where(Commit.hash == item["hash"])
                existing = db.execute(stmt).scalar_one_or_none()

                if existing:
                    # Update fields and associate with execution if provided
                    existing.execution_id = execution_id or existing.execution_id
                    existing.author = item["author"]
                    existing.message = item["message"]
                    existing.commit_date = item["commit_date"]
                    existing.files_changed = item["files_changed"]
                    existing.repo_name = item.get("repo_name")
                    existing.repo_path = item.get("repo_path")
                    if item.get("commit_url"):
                        existing.commit_url = item["commit_url"]
                    if item.get("xml_tags_metrics") is not None:
                        existing.xml_tags_metrics = item["xml_tags_metrics"]
                    if item.get("ic_count") is not None:
                        existing.ic_count = item["ic_count"]
                    saved_records.append(existing)
                else:
                    new_commit = Commit(
                        hash=item["hash"],
                        author=item["author"],
                        message=item["message"],
                        commit_date=item["commit_date"],
                        files_changed=item["files_changed"],
                        repo_name=item.get("repo_name"),
                        repo_path=item.get("repo_path"),
                        commit_url=item.get("commit_url"),
                        xml_tags_metrics=item.get("xml_tags_metrics"),
                        ic_count=item.get("ic_count", 0),
                        execution_id=execution_id,
                    )
                    db.add(new_commit)
                    saved_records.append(new_commit)

            db.commit()
            for rec in saved_records:
                db.refresh(rec)

            logger.info(f"{len(saved_records)} commits salvos/atualizados com sucesso no PostgreSQL.")
            return saved_records
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao persistir commits no banco de dados: {exc}")
            raise

    @classmethod
    def execute_analysis(
        cls,
        db: Session,
        repo_path: str | Path,
        start_date: datetime,
        end_date: datetime,
        author: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Tuple[ExecutionHistory, List[Commit]]:
        """Run complete extraction pipeline: record history, fetch commits, and save to DB."""
        path = Path(repo_path).resolve()
        logger.info(f"Iniciando ciclo de execução de análise para o período {start_date} até {end_date}")

        # 1. Create Execution History record
        history = ExecutionHistory(
            start_date=start_date,
            end_date=end_date,
            repo_path=str(path),
            total_commits=0,
            total_meetings=0,
            total_catalog_items=0,
            status="processando",
            notes=notes,
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        try:
            # 2. Fetch commits from Git
            commits_data = cls.get_commits(
                repo_path=path,
                start_date=start_date,
                end_date=end_date,
                author=author,
            )

            # 3. Save to database
            saved_commits = cls.save_commits(
                db=db,
                commits_data=commits_data,
                execution_id=history.id,
            )

            # 4. Update history totals
            history.total_commits = len(saved_commits)
            history.status = "concluido"
            db.commit()
            db.refresh(history)

            logger.info(
                f"Execução #{history.id} concluída com sucesso: {history.total_commits} commits registrados."
            )
            return history, saved_commits

        except Exception as exc:
            history.status = "erro"
            history.notes = f"Falha na execução: {str(exc)}"
            db.commit()
            logger.error(f"Execução #{history.id} finalizou com erro: {exc}")
            raise
