from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def normalize_xml_metrics(raw: Any, default_count: int = 0) -> Dict[str, Any]:
    """Normalize raw xml_tags_metrics into a standard dict containing added/removed and counts."""
    if not isinstance(raw, dict):
        return {
            "added": {},
            "removed": {},
            "total_added": 0,
            "total_removed": 0,
            "total_ics": default_count or 0,
        }
    if "added" in raw or "removed" in raw:
        added = raw.get("added") or {}
        removed = raw.get("removed") or {}
        total_added = raw.get("total_added", sum(added.values()))
        total_removed = raw.get("total_removed", sum(removed.values()))
        total_ics = raw.get("total_ics", total_added + total_removed)
        return {
            "added": added,
            "removed": removed,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_ics": total_ics or default_count or 0,
        }
    # Backward compatibility for flat dict {tag: count}
    total_added = sum(raw.values())
    return {
        "added": raw,
        "removed": {},
        "total_added": total_added,
        "total_removed": 0,
        "total_ics": default_count or total_added,
    }


def format_ic_details(parsed_metrics: Dict[str, Any], ic_count: int = 0) -> List[str]:
    """Helper to generate detailed IC calculation lines showing additions and removals."""
    total_ics = ic_count or parsed_metrics.get("total_ics", 0)
    if total_ics <= 0:
        return []

    lines: List[str] = [""]
    added_cnt = parsed_metrics.get("total_added", 0)
    removed_cnt = parsed_metrics.get("total_removed", 0)

    if added_cnt > 0 and removed_cnt > 0:
        summary_str = f" ({added_cnt} adicionadas, {removed_cnt} removidas)"
    elif added_cnt > 0:
        summary_str = f" (+{added_cnt} adições)"
    elif removed_cnt > 0:
        summary_str = f" (-{removed_cnt} remoções)"
    else:
        summary_str = ""

    lines.append(f"Itens de Catálogo (IC) calculados: {total_ics} IC(s){summary_str}")

    added_tags = parsed_metrics.get("added", {})
    removed_tags = parsed_metrics.get("removed", {})

    if added_tags or removed_tags:
        lines.append("Detalhamento das tags XML (regras do PJE):")
        if added_tags:
            lines.append(f"- Tags Adicionadas (+{added_cnt}):")
            for tag, count in sorted(added_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  * <{tag}>: {count}")
        if removed_tags:
            lines.append(f"- Tags Removidas (-{removed_cnt}):")
            for tag, count in sorted(removed_tags.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  * <{tag}>: {count}")

    return lines


class Commit(Base):
    """Stores Git commit information retrieved by Productivity Assistant."""

    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    commit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    files_changed: Mapped[Any] = mapped_column(JSON, nullable=True)  # List of changed file names/stats
    repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    repo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    commit_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    xml_tags_metrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # Dict of {tag: count}
    ic_count: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    execution_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("execution_history.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    execution: Mapped[Optional["ExecutionHistory"]] = relationship("ExecutionHistory", back_populates="commits")

    def __repr__(self) -> str:
        return f"<Commit {self.hash[:7]} by {self.author} on {self.commit_date}>"

    @property
    def short_hash(self) -> str:
        return self.hash[:7] if self.hash else ""

    @property
    def web_commit_url(self) -> Optional[str]:
        """Return the web link for the commit (GitHub, GitLab, etc.)."""
        if self.commit_url:
            return self.commit_url
        if self.repo_path:
            try:
                from app.services.git_service import GitService
                derived = GitService.get_commit_url(self.repo_path, self.hash)
                if derived:
                    return derived
            except Exception:
                pass
        return None

    @property
    def files_count(self) -> int:
        if isinstance(self.files_changed, list):
            return len(self.files_changed)
        if isinstance(self.files_changed, dict):
            return len(self.files_changed.keys())
        return 0

    @property
    def xml_files(self) -> List[Any]:
        """Return list of modified XML files with their diff metrics."""
        results = []
        if isinstance(self.files_changed, list):
            for item in self.files_changed:
                if isinstance(item, dict):
                    if item.get("is_xml") or str(item.get("path", "")).lower().endswith(".xml"):
                        results.append(item)
                elif isinstance(item, str) and item.lower().endswith(".xml"):
                    results.append({
                        "path": item,
                        "filename": item.split("/")[-1].split("\\")[-1],
                        "is_xml": True,
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return results

    @property
    def xml_files_count(self) -> int:
        return len(self.xml_files)

    @property
    def xml_insertions(self) -> int:
        return sum(f.get("insertions", 0) for f in self.xml_files)

    @property
    def xml_deletions(self) -> int:
        return sum(f.get("deletions", 0) for f in self.xml_files)

    @property
    def xml_total_edits(self) -> int:
        return self.xml_insertions + self.xml_deletions

    @property
    def has_xml_changes(self) -> bool:
        return self.xml_files_count > 0

    @property
    def ic_metrics_parsed(self) -> Dict[str, Any]:
        return normalize_xml_metrics(getattr(self, "xml_tags_metrics", None), getattr(self, "ic_count", 0) or 0)

    @property
    def ic_added_count(self) -> int:
        return self.ic_metrics_parsed["total_added"]

    @property
    def ic_removed_count(self) -> int:
        return self.ic_metrics_parsed["total_removed"]

    @property
    def ic_title(self) -> str:
        first_line = (self.message or "").strip().split("\n")[0].strip() if self.message else "Atividade de Desenvolvimento"
        return first_line[:180]

    @property
    def ic_description(self) -> str:
        date_str = self.commit_date.strftime("%d/%m/%Y %H:%M") if self.commit_date else ""
        link = self.web_commit_url or self.commit_url or ""
        lines = [
            f"Commit: {self.short_hash}",
            f"Data: {date_str}",
            f"Autor: {self.author}",
        ]
        if link:
            lines.append(f"Link: {link}")
        lines.append("")
        lines.append("Descrição:")
        lines.append(self.message.strip() if self.message else "")
        if self.files_changed:
            lines.append("")
            lines.append("Arquivos Alterados:")
            xml_count = 0
            for f in self.files_changed:
                if isinstance(f, dict):
                    path = f.get("path") or f.get("filename") or ""
                    ins = f.get("insertions", 0)
                    dels = f.get("deletions", 0)
                    diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
                    if f.get("is_xml") or path.lower().endswith(".xml"):
                        xml_count += 1
                        lines.append(f"- [XML] {path}{diff_info}")
                    else:
                        lines.append(f"- {path}{diff_info}")
                else:
                    lines.append(f"- {f}")
            if xml_count > 0:
                lines.append(f"(Total de arquivos XML alterados: {xml_count})")

        lines.extend(format_ic_details(self.ic_metrics_parsed, getattr(self, "ic_count", 0) or 0))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        parsed_metrics = self.ic_metrics_parsed
        return {
            "id": self.id,
            "hash": self.hash,
            "short_hash": self.short_hash,
            "author": self.author,
            "commit_date": self.commit_date.strftime("%d/%m/%Y %H:%M") if self.commit_date else "",
            "message": self.message,
            "repo_name": self.repo_name or "",
            "repo_path": self.repo_path or "",
            "commit_url": self.web_commit_url or self.commit_url or "",
            "files_changed": self.files_changed or [],
            "files_count": self.files_count,
            "xml_files_count": self.xml_files_count,
            "xml_insertions": self.xml_insertions,
            "xml_deletions": self.xml_deletions,
            "has_xml_changes": self.has_xml_changes,
            "xml_tags_metrics": parsed_metrics,
            "ic_count": getattr(self, "ic_count", 0) or parsed_metrics["total_ics"],
            "ic_added_count": self.ic_added_count,
            "ic_removed_count": self.ic_removed_count,
            "ic_title": self.ic_title,
            "ic_description": self.ic_description,
        }


class CommitItem:
    """In-memory representation of a git commit with XML and web url helpers."""

    def __init__(self, data: Dict[str, Any]):
        self.id = None
        self.hash = data.get("hash", "")
        self.author = data.get("author", "")
        self.author_name = data.get("author_name", "")
        self.author_email = data.get("author_email", "")
        self.commit_date = data.get("commit_date")
        self.message = data.get("message", "")
        self.files_changed = data.get("files_changed", [])
        self.repo_name = data.get("repo_name", "")
        self.repo_path = data.get("repo_path", "")
        self.commit_url = data.get("commit_url", "")
        self.xml_tags_metrics = data.get("xml_tags_metrics") or {}
        self.ic_count = data.get("ic_count") or 0

    @property
    def short_hash(self) -> str:
        return self.hash[:7] if self.hash else ""

    @property
    def web_commit_url(self) -> Optional[str]:
        return self.commit_url or None

    @property
    def files_count(self) -> int:
        return len(self.files_changed) if isinstance(self.files_changed, list) else 0

    @property
    def xml_files(self) -> List[Any]:
        results = []
        if isinstance(self.files_changed, list):
            for item in self.files_changed:
                if isinstance(item, dict):
                    if item.get("is_xml") or str(item.get("path", "")).lower().endswith(".xml"):
                        results.append(item)
                elif isinstance(item, str) and item.lower().endswith(".xml"):
                    results.append({
                        "path": item,
                        "filename": item.split("/")[-1].split("\\")[-1],
                        "is_xml": True,
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return results

    @property
    def xml_files_count(self) -> int:
        return len(self.xml_files)

    @property
    def xml_insertions(self) -> int:
        return sum(f.get("insertions", 0) for f in self.xml_files)

    @property
    def xml_deletions(self) -> int:
        return sum(f.get("deletions", 0) for f in self.xml_files)

    @property
    def xml_total_edits(self) -> int:
        return self.xml_insertions + self.xml_deletions

    @property
    def has_xml_changes(self) -> bool:
        return self.xml_files_count > 0

    @property
    def ic_metrics_parsed(self) -> Dict[str, Any]:
        return normalize_xml_metrics(self.xml_tags_metrics, self.ic_count or 0)

    @property
    def ic_added_count(self) -> int:
        return self.ic_metrics_parsed["total_added"]

    @property
    def ic_removed_count(self) -> int:
        return self.ic_metrics_parsed["total_removed"]

    @property
    def ic_title(self) -> str:
        first_line = (self.message or "").strip().split("\n")[0].strip() if self.message else "Atividade de Desenvolvimento"
        return first_line[:180]

    @property
    def ic_description(self) -> str:
        date_str = ""
        if self.commit_date:
            try:
                date_str = self.commit_date.strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = str(self.commit_date)
        link = self.web_commit_url or self.commit_url or ""
        lines = [
            f"Commit: {self.short_hash}",
            f"Data: {date_str}",
            f"Autor: {self.author}",
        ]
        if link:
            lines.append(f"Link: {link}")
        lines.append("")
        lines.append("Descrição:")
        lines.append(self.message.strip() if self.message else "")
        if self.files_changed:
            lines.append("")
            lines.append("Arquivos Alterados:")
            xml_count = 0
            for f in self.files_changed:
                if isinstance(f, dict):
                    path = f.get("path") or f.get("filename") or ""
                    ins = f.get("insertions", 0)
                    dels = f.get("deletions", 0)
                    diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
                    if f.get("is_xml") or path.lower().endswith(".xml"):
                        xml_count += 1
                        lines.append(f"- [XML] {path}{diff_info}")
                    else:
                        lines.append(f"- {path}{diff_info}")
                else:
                    lines.append(f"- {f}")
            if xml_count > 0:
                lines.append(f"(Total de arquivos XML alterados: {xml_count})")

        lines.extend(format_ic_details(self.ic_metrics_parsed, self.ic_count or 0))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        date_str = ""
        if self.commit_date:
            try:
                date_str = self.commit_date.strftime("%d/%m/%Y %H:%M")
            except Exception:
                date_str = str(self.commit_date)
        parsed_metrics = self.ic_metrics_parsed
        return {
            "id": self.id,
            "hash": self.hash,
            "short_hash": self.short_hash,
            "author": self.author,
            "commit_date": date_str,
            "message": self.message,
            "repo_name": self.repo_name or "",
            "repo_path": self.repo_path or "",
            "commit_url": self.web_commit_url or self.commit_url or "",
            "files_changed": self.files_changed or [],
            "files_count": self.files_count,
            "xml_files_count": self.xml_files_count,
            "xml_insertions": self.xml_insertions,
            "xml_deletions": self.xml_deletions,
            "has_xml_changes": self.has_xml_changes,
            "xml_tags_metrics": parsed_metrics,
            "ic_count": self.ic_count or parsed_metrics["total_ics"],
            "ic_added_count": self.ic_added_count,
            "ic_removed_count": self.ic_removed_count,
            "ic_title": self.ic_title,
            "ic_description": self.ic_description,
        }

