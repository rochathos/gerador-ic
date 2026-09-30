from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.logger import logger
from app.models.commit import Commit
from app.models.execution_history import ExecutionHistory


class GitService:
    """Service to interact with local Git repositories using GitPython."""

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
    def get_commits(
        cls,
        repo_path: str | Path,
        start_date: datetime,
        end_date: datetime,
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

        # Ensure start and end datetimes have timezone info for accurate comparison
        if start_date.tzinfo is None:
            start_date_tz = start_date.replace(tzinfo=timezone.utc)
        else:
            start_date_tz = start_date

        if end_date.tzinfo is None:
            end_date_tz = end_date.replace(tzinfo=timezone.utc)
        else:
            end_date_tz = end_date

        # Convert to timestamps for git log query efficiency
        since_ts = int(start_date_tz.timestamp())
        until_ts = int(end_date_tz.timestamp())

        commits_found: List[Dict[str, Any]] = []

        try:
            # We iterate through all branches/commits
            # Passing --all ensures commits on any branch are retrieved
            iter_kwargs: Dict[str, Any] = {
                "all": True,
                "since": since_ts,
                "until": until_ts,
            }

            for commit in repo.iter_commits(**iter_kwargs):
                commit_dt = commit.committed_datetime

                # Safety check against time boundaries
                if not (start_date_tz <= commit_dt <= end_date_tz):
                    continue

                # Filter by author if provided
                if author:
                    author_query = author.strip().lower()
                    author_name = (commit.author.name or "").lower()
                    author_email = (commit.author.email or "").lower()
                    if author_query not in author_name and author_query not in author_email:
                        continue

                # Get changed files safely
                files_changed: List[str] = []
                try:
                    stats = commit.stats
                    files_changed = list(stats.files.keys())
                except Exception as stat_err:
                    logger.debug(f"Não foi possível obter stats do commit {commit.hexsha[:7]}: {stat_err}")
                    try:
                        if commit.parents:
                            diff = commit.diff(commit.parents[0])
                            files_changed = [d.a_path or d.b_path for d in diff if d.a_path or d.b_path]
                    except Exception:
                        files_changed = []

                commit_author_display = f"{commit.author.name} <{commit.author.email}>" if commit.author.email else commit.author.name

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
