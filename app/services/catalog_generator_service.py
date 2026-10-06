from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.logger import logger
from app.models.catalog_item import CatalogItem
from app.models.commit import normalize_xml_metrics, format_ic_details, decode_git_path, build_ic_description


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
            raw_xml_tags = commit.get("xml_tags_metrics") or {}
            ic_count = commit.get("ic_count", 0) or 0
        else:
            msg = commit.message.strip()
            commit_hash = commit.hash
            short_hash = commit.short_hash
            author = commit.author
            commit_date = commit.commit_date
            commit_url = commit.web_commit_url or commit.commit_url or ""
            files_changed = commit.files_changed or []
            raw_xml_tags = getattr(commit, "xml_tags_metrics", {}) or {}
            ic_count = getattr(commit, "ic_count", 0) or 0

        parsed_metrics = normalize_xml_metrics(raw_xml_tags, ic_count)
        total_ics = ic_count or parsed_metrics.get("total_ics", 0)

        # Title: first line of commit message
        first_line = msg.split("\n")[0].strip() if msg else "Atividade de Desenvolvimento"
        title = first_line[:180]

        description = build_ic_description(
            short_hash=short_hash,
            commit_date=commit_date,
            author=author,
            message=msg,
            commit_url=commit_url,
            files_changed=files_changed,
            xml_tags_metrics=raw_xml_tags,
            ic_count=total_ics,
        )

        return {
            "title": title,
            "description": description,
            "status": "sugerido",
            "commit_hash": commit_hash,
            "commit_url": commit_url,
            "ic_count": total_ics,
            "xml_tags_metrics": parsed_metrics,
        }
