from datetime import datetime
from typing import List
from sqlalchemy import Integer, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ExecutionHistory(Base):
    """Stores history of each batch analysis execution."""

    __tablename__ = "execution_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_commits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_meetings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_catalog_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repo_path: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="concluido", nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    commits: Mapped[List["Commit"]] = relationship("Commit", back_populates="execution", cascade="all, delete-orphan")
    meetings: Mapped[List["Meeting"]] = relationship("Meeting", back_populates="execution", cascade="all, delete-orphan")
    catalog_items: Mapped[List["CatalogItem"]] = relationship("CatalogItem", back_populates="execution", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ExecutionHistory id={self.id} {self.start_date.isoformat()} to {self.end_date.isoformat()}>"
