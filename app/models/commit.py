from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


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


def normalize_xml_metrics(raw: Any, default_count: int = 0) -> Dict[str, Any]:
    """Normalize raw xml_tags_metrics into a standard dict containing added/removed, flows, and counts."""
    if not isinstance(raw, dict):
        return {
            "added": {},
            "removed": {},
            "total_added": 0,
            "total_removed": 0,
            "total_ics": default_count or 0,
            "flows": {},
        }
    if "added" in raw or "removed" in raw or "flows" in raw:
        added = raw.get("added") or {}
        removed = raw.get("removed") or {}
        total_added = raw.get("total_added", sum(added.values()))
        total_removed = raw.get("total_removed", sum(removed.values()))
        total_ics = raw.get("total_ics", total_added + total_removed)
        flows = raw.get("flows") or {}
        return {
            "added": added,
            "removed": removed,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_ics": total_ics or default_count or 0,
            "flows": flows,
        }
    # Backward compatibility for flat dict {tag: count}
    total_added = sum(raw.values())
    return {
        "added": raw,
        "removed": {},
        "total_added": total_added,
        "total_removed": 0,
        "total_ics": default_count or total_added,
        "flows": {},
    }


def format_ic_details(parsed_metrics: Dict[str, Any], ic_count: int = 0) -> List[str]:
    """Helper to generate detailed IC calculation lines showing additions and removals per flow (XML file)."""
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

    flows = parsed_metrics.get("flows") or {}
    if flows:
        lines.append("")
        lines.append("Detalhamento por Fluxo (regras do PJE):")
        for path, flow_data in flows.items():
            f_added = flow_data.get("added", {})
            f_removed = flow_data.get("removed", {})
            f_total_added = flow_data.get("total_added", sum(f_added.values()))
            f_total_removed = flow_data.get("total_removed", sum(f_removed.values()))
            f_total_ics = flow_data.get("total_ics", f_total_added + f_total_removed)

            if f_total_ics == 0:
                continue

            lines.append("")
            lines.append(f"Fluxo: {path}")
            if f_added:
                lines.append(f"- Tags Adicionadas (+{f_total_added}):")
                for tag, count in sorted(f_added.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  * <{tag}>: {count}")
            if f_removed:
                lines.append(f"- Tags Removidas (-{f_total_removed}):")
                for tag, count in sorted(f_removed.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  * <{tag}>: {count}")
    else:
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


def find_flow_metrics_for_file(path: str, flows: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Match a file path against the flows dictionary by exact path, normalized path, or basename."""
    if not flows or not path:
        return None
    if path in flows:
        return flows[path]
    norm_path = path.replace("\\", "/").strip().lower()
    for f_path, f_data in flows.items():
        if f_path.replace("\\", "/").strip().lower() == norm_path:
            return f_data
    base = norm_path.split("/")[-1]
    for f_path, f_data in flows.items():
        if f_path.replace("\\", "/").strip().lower().split("/")[-1] == base:
            return f_data
    return None


def format_flow_tags_lines(flow_data: Dict[str, Any]) -> List[str]:
    """Format tags touched for a specific flow into compact bullet lines."""
    lines: List[str] = []
    f_added = flow_data.get("added", {})
    f_removed = flow_data.get("removed", {})
    f_total_added = flow_data.get("total_added", sum(f_added.values()))
    f_total_removed = flow_data.get("total_removed", sum(f_removed.values()))

    if f_added:
        add_items = [f"<{t}>: {c}" for t, c in sorted(f_added.items(), key=lambda x: x[1], reverse=True)]
        lines.append(f"  * Tags Adicionadas (+{f_total_added}): {', '.join(add_items)}")
    if f_removed:
        rem_items = [f"<{t}>: {c}" for t, c in sorted(f_removed.items(), key=lambda x: x[1], reverse=True)]
        lines.append(f"  * Tags Removidas (-{f_total_removed}): {', '.join(rem_items)}")

    return lines


def build_ic_description(
    short_hash: str,
    commit_date: Any,
    author: str,
    message: str,
    commit_url: str = "",
    files_changed: Optional[List[Any]] = None,
    xml_tags_metrics: Optional[Dict[str, Any]] = None,
    ic_count: int = 0,
) -> str:
    """Build the clean, compact Redmine IC description.

    Tags touched are displayed directly below each altered XML file (fluxo) in 'Arquivos Alterados:',
    making the text shorter, more readable, and avoiding duplicate flow sections.
    """
    date_str = ""
    if commit_date:
        try:
            date_str = commit_date.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = str(commit_date)

    parsed_metrics = normalize_xml_metrics(xml_tags_metrics or {}, ic_count)
    total_ics = ic_count or parsed_metrics.get("total_ics", 0)
    flows = parsed_metrics.get("flows") or {}

    lines = [
        f"Commit: {short_hash}",
        f"Data: {date_str}",
        f"Autor: {author}",
    ]
    if commit_url:
        lines.append(f"Link: {commit_url}")

    lines.append("")
    lines.append("Descrição:")
    lines.append(message.strip() if message else "")

    added_cnt = parsed_metrics.get("total_added", 0)
    removed_cnt = parsed_metrics.get("total_removed", 0)
    if total_ics > 0:
        if added_cnt > 0 and removed_cnt > 0:
            summary_str = f" ({added_cnt} adicionadas, {removed_cnt} removidas)"
        elif added_cnt > 0:
            summary_str = f" (+{added_cnt} adições)"
        elif removed_cnt > 0:
            summary_str = f" (-{removed_cnt} remoções)"
        else:
            summary_str = ""
        lines.append("")
        lines.append(f"Itens de Catálogo (IC) calculados: {total_ics} IC(s){summary_str}")

    clean_files = files_changed or []
    if clean_files:
        lines.append("")
        lines.append("Arquivos Alterados:")
        xml_count = 0
        matched_flow_paths = set()

        for f in clean_files:
            if isinstance(f, dict):
                raw_path = f.get("path") or f.get("filename") or ""
                path = decode_git_path(raw_path)
                ins = f.get("insertions", 0)
                dels = f.get("deletions", 0)
                diff_info = f" (+{ins} / -{dels})" if (ins or dels) else ""
                is_xml = f.get("is_xml") or path.lower().endswith(".xml")
            else:
                path = decode_git_path(str(f))
                diff_info = ""
                is_xml = path.lower().endswith(".xml")

            if is_xml:
                xml_count += 1
                lines.append(f"- [XML] {path}{diff_info}")
                flow_data = find_flow_metrics_for_file(path, flows)
                if flow_data:
                    matched_flow_paths.add(flow_data.get("path", path))
                    lines.extend(format_flow_tags_lines(flow_data))
            else:
                lines.append(f"- {path}{diff_info}")

        # In case some flows were not in files_changed (fallback)
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0 and f_path not in matched_flow_paths:
                flow_check = find_flow_metrics_for_file(f_path, {p: {} for p in matched_flow_paths})
                if not flow_check:
                    xml_count += 1
                    lines.append(f"- [XML] {f_path}")
                    lines.extend(format_flow_tags_lines(f_data))

        if xml_count > 0:
            lines.append(f"(Total de arquivos XML alterados: {xml_count})")
    elif flows:
        lines.append("")
        lines.append("Arquivos Alterados:")
        xml_count = 0
        for f_path, f_data in flows.items():
            if f_data.get("total_ics", 0) > 0:
                xml_count += 1
                lines.append(f"- [XML] {f_path}")
                lines.extend(format_flow_tags_lines(f_data))
        if xml_count > 0:
            lines.append(f"(Total de arquivos XML alterados: {xml_count})")
    elif total_ics > 0 and (added_cnt > 0 or removed_cnt > 0):
        lines.append("")
        lines.append("Tags XML Alteradas:")
        added_tags = parsed_metrics.get("added", {})
        removed_tags = parsed_metrics.get("removed", {})
        if added_tags:
            add_items = [f"<{t}>: {c}" for t, c in sorted(added_tags.items(), key=lambda x: x[1], reverse=True)]
            lines.append(f"- Tags Adicionadas (+{added_cnt}): {', '.join(add_items)}")
        if removed_tags:
            rem_items = [f"<{t}>: {c}" for t, c in sorted(removed_tags.items(), key=lambda x: x[1], reverse=True)]
            lines.append(f"- Tags Removidas (-{removed_cnt}): {', '.join(rem_items)}")

    return "\n".join(lines)


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
    def files_changed_clean(self) -> List[Dict[str, Any]]:
        """Return files_changed with octal escapes decoded into proper UTF-8 accents."""
        cleaned = []
        if isinstance(self.files_changed, list):
            for f in self.files_changed:
                if isinstance(f, dict):
                    f_copy = dict(f)
                    raw_path = f.get("path") or f.get("filename") or ""
                    clean_path = decode_git_path(raw_path)
                    f_copy["path"] = clean_path
                    f_copy["filename"] = clean_path.split("/")[-1].split("\\")[-1]
                    f_copy["is_xml"] = f.get("is_xml") or clean_path.lower().endswith(".xml")
                    cleaned.append(f_copy)
                else:
                    clean_path = decode_git_path(str(f))
                    cleaned.append({
                        "path": clean_path,
                        "filename": clean_path.split("/")[-1].split("\\")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return cleaned

    @property
    def xml_files(self) -> List[Any]:
        """Return list of modified XML files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_xml")]

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
        return build_ic_description(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=getattr(self, "ic_count", 0) or 0,
        )

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
            "files_changed": self.files_changed_clean,
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
    def files_changed_clean(self) -> List[Dict[str, Any]]:
        """Return files_changed with octal escapes decoded into proper UTF-8 accents."""
        cleaned = []
        if isinstance(self.files_changed, list):
            for f in self.files_changed:
                if isinstance(f, dict):
                    f_copy = dict(f)
                    raw_path = f.get("path") or f.get("filename") or ""
                    clean_path = decode_git_path(raw_path)
                    f_copy["path"] = clean_path
                    f_copy["filename"] = clean_path.split("/")[-1].split("\\")[-1]
                    f_copy["is_xml"] = f.get("is_xml") or clean_path.lower().endswith(".xml")
                    cleaned.append(f_copy)
                else:
                    clean_path = decode_git_path(str(f))
                    cleaned.append({
                        "path": clean_path,
                        "filename": clean_path.split("/")[-1].split("\\")[-1],
                        "is_xml": clean_path.lower().endswith(".xml"),
                        "insertions": 0,
                        "deletions": 0,
                        "lines": 0,
                    })
        return cleaned

    @property
    def xml_files(self) -> List[Any]:
        """Return list of modified XML files with their diff metrics."""
        return [f for f in self.files_changed_clean if f.get("is_xml")]

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
        return build_ic_description(
            short_hash=self.short_hash,
            commit_date=self.commit_date,
            author=self.author,
            message=self.message,
            commit_url=self.web_commit_url or self.commit_url or "",
            files_changed=self.files_changed_clean,
            xml_tags_metrics=self.xml_tags_metrics,
            ic_count=self.ic_count or 0,
        )

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
            "files_changed": self.files_changed_clean,
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

