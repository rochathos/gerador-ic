from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.logger import logger
from app.models.meeting import Meeting


class MeetingService:
    """Service to handle meetings (e.g. Teams, Outlook calendar).

    Prepared for future Microsoft Teams integration (Phase 2).
    """

    @classmethod
    def get_meetings(
        cls,
        start_date: datetime,
        end_date: datetime,
        user_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch meetings within the specified time period.

        Initial implementation is ready for future Teams integration.
        """
        logger.info(
            f"Buscando reuniões entre {start_date} e {end_date} (usuário: {user_email or 'padrão'})"
        )
        # Placeholder returning empty list or registered meetings
        return []

    @classmethod
    def save_meetings(
        cls,
        db: Session,
        meetings_data: List[Dict[str, Any]],
        execution_id: Optional[int] = None,
    ) -> List[Meeting]:
        """Persist meetings into PostgreSQL."""
        saved: List[Meeting] = []
        try:
            for item in meetings_data:
                meeting = Meeting(
                    title=item["title"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    duration=item.get("duration", "30m"),
                    execution_id=execution_id,
                )
                db.add(meeting)
                saved.append(meeting)
            db.commit()
            for m in saved:
                db.refresh(m)
            logger.info(f"{len(saved)} reuniões salvas no PostgreSQL.")
            return saved
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao salvar reuniões: {exc}")
            raise
