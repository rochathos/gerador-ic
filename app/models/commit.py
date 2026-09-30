from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


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
