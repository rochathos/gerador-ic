from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Meeting(Base):
    """Stores meeting information (e.g. Teams, Outlook calendar)."""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "45m" or "1h 30m"
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    call_type: Mapped[Optional[str]] = mapped_column(String(50), default="reuniao", nullable=True)
    redmine_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pendente", nullable=False)
    execution_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("execution_history.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    execution: Mapped[Optional["ExecutionHistory"]] = relationship("ExecutionHistory", back_populates="meetings")

    @property
    def is_saved(self) -> bool:
        override = getattr(self, "_is_saved_override", None)
        if override is not None:
            return override
        return (self.status in ("criado", "salvo")) or bool(self.redmine_id)

    @is_saved.setter
    def is_saved(self, val: bool) -> None:
        self._is_saved_override = val

    def __repr__(self) -> str:
        return f"<Meeting {self.title} ({self.duration})>"
