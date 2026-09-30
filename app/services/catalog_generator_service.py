from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.logger import logger
from app.models.catalog_item import CatalogItem


class CatalogGeneratorService:
    """Generates Catalog Items (ICs) for commits - 1 IC per commit."""

    @classmethod
    def generate_ic_for_commit(cls, commit: Any) -> Dict[str, Any]:
        """Generate a single Catalog Item (IC) tailored to a single commit."""
        # Extract fields whether commit is an ORM object or dictionary
        if isinstance(commit, dict):
            msg = commit.get("message", "").strip()
            commit_hash = commit.get("hash", "")
            short_hash = commit_hash[:7] if commit_hash else ""
            author = commit.get("author", "")
            commit_date = commit.get("commit_date")
            commit_url = commit.get("commit_url") or ""
            files_changed = commit.get("files_changed") or []
        else:
            msg = commit.message.strip()
            commit_hash = commit.hash
            short_hash = commit.short_hash
            author = commit.author
            commit_date = commit.commit_date
            commit_url = commit.web_commit_url or commit.commit_url or ""
            files_changed = commit.files_changed or []

        # Title: first line of commit message
        first_line = msg.split("\n")[0].strip() if msg else "Atividade de Desenvolvimento"
        title = first_line[:180]

        # Date formatting
        date_str = ""
        if commit_date:
            try:
                date_str = commit_date.strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = str(commit_date)

        # Build clean, detailed description for Redmine IC
        desc_lines = [
            f"Commit: {short_hash}",
            f"Data: {date_str}",
            f"Autor: {author}",
        ]
        if commit_url:
            desc_lines.append(f"Link: {commit_url}")

        desc_lines.append("")
        desc_lines.append("Descrição:")
        desc_lines.append(msg)

        # Files changed and XML highlights
        if files_changed:
            desc_lines.append("")
            desc_lines.append("Arquivos Alterados:")
            xml_count = 0
            for f in files_changed:
                if isinstance(f, dict):
                    path = f.get("path") or f.get("filename") or ""
                    ins = f.get("insertions", 0)
                    dels = f.get("deletions", 0)
                    diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
                    if f.get("is_xml") or path.lower().endswith(".xml"):
                        xml_count += 1
                        desc_lines.append(f"- [XML] {path}{diff_info}")
                    else:
                        desc_lines.append(f"- {path}{diff_info}")
                else:
                    desc_lines.append(f"- {f}")

            if xml_count > 0:
                desc_lines.append(f"(Total de arquivos XML alterados: {xml_count})")

        description = "\n".join(desc_lines)

        return {
            "title": title,
            "description": description,
            "status": "sugerido",
            "commit_hash": commit_hash,
            "commit_url": commit_url,
        }

    @classmethod
    def generate_suggestions(
        cls,
        commits: List[Any],
        meetings: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate 1 Catalog Item (IC) proposal for EACH commit."""
        if not commits:
            return []

        logger.info(f"Gerando IC individual para cada um dos {len(commits)} commits...")
        suggestions: List[Dict[str, Any]] = [
            cls.generate_ic_for_commit(c) for c in commits
        ]
        return suggestions

    @classmethod
    def save_suggestions(
        cls,
        db: Session,
        suggestions: List[Dict[str, Any]],
        execution_id: Optional[int] = None,
    ) -> List[CatalogItem]:
        """Save generated Catalog Items into the database."""
        created_items: List[CatalogItem] = []
        try:
            for s in suggestions:
                item = CatalogItem(
                    title=s["title"],
                    description=s["description"],
                    status=s.get("status", "sugerido"),
                    execution_id=execution_id,
                )
                db.add(item)
                created_items.append(item)
            db.commit()
            for item in created_items:
                db.refresh(item)
            logger.info(f"{len(created_items)} ICs individuais salvos no PostgreSQL.")
            return created_items
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao salvar ICs: {exc}")
            raise
