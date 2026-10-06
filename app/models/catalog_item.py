from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CatalogItem(Base):
    """Stores generated Catalog Items (Itens de Catálogo - IC) for Redmine."""

    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    redmine_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="salvo", nullable=False, index=True
    )  # salvo, criado, ignorado, sugerido
    commit_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    natureza: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # fluxo, sql
    activity_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ic_count: Mapped[Optional[int]] = mapped_column(Integer, default=1, nullable=True)
    execution_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("execution_history.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    execution: Mapped[Optional["ExecutionHistory"]] = relationship("ExecutionHistory", back_populates="catalog_items")

    def __repr__(self) -> str:
        return f"<CatalogItem id={self.id} status={self.status} natureza={self.natureza} redmine_id={self.redmine_id} title={self.title[:30]}>"

