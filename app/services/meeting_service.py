import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc

from app.core.logger import logger
from app.models.meeting import Meeting
from app.services.redmine_service import RedmineService


class MeetingService:
    """Service to handle Microsoft Teams calls, meetings, and Redmine IC generation."""

    DEFAULT_ACTIVITY_TYPE = "Gestão - Participação em reunião, exceto reunião de levantamento de requisitos"

    @staticmethod
    def parse_datetime_flexible(dt_raw: Any) -> datetime:
        """Parse various date formats from Teams Web into a Python datetime."""
        if isinstance(dt_raw, datetime):
            return dt_raw

        now = datetime.now()
        if not dt_raw or not isinstance(dt_raw, str):
            return now

        clean = dt_raw.strip().lower()

        # Month mapping for Portuguese dates
        months = {
            "janeiro": 1, "jan": 1,
            "fevereiro": 2, "fev": 2,
            "março": 3, "marco": 3, "mar": 3,
            "abril": 4, "abr": 4,
            "maio": 5, "mai": 5,
            "junho": 6, "jun": 6,
            "julho": 7, "jul": 7,
            "agosto": 8, "ago": 8,
            "setembro": 9, "set": 9,
            "outubro": 10, "out": 10,
            "novembro": 11, "nov": 11,
            "dezembro": 12, "dez": 12,
        }

        # Check for HH:MM time inside the string
        time_match = re.search(r"(\d{1,2})[:h](\d{2})", clean)
        hour = int(time_match.group(1)) if time_match else 9
        minute = int(time_match.group(2)) if time_match else 0

        # Handle "Hoje"
        if "hoje" in clean:
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Handle "Ontem"
        if "ontem" in clean:
            yesterday = now - timedelta(days=1)
            return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Handle "28 de setembro" or "28 set"
        pt_m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-zç]+)", clean)
        if pt_m:
            day = int(pt_m.group(1))
            m_str = pt_m.group(2)
            if m_str in months:
                month_num = months[m_str]
                year = now.year
                if month_num > now.month:
                    year -= 1
                return datetime(year, month_num, day, hour, minute)

        # Handle standard ISO formats: 2026-10-01T10:15:00
        try:
            return datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass

        # Handle formats like "01/10/2026 10:15" or "01/10"
        num_m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", clean)
        if num_m:
            day = int(num_m.group(1))
            month_num = int(num_m.group(2))
            year = int(num_m.group(3)) if num_m.group(3) else now.year
            if year < 100:
                year += 2000
            return datetime(year, month_num, day, hour, minute)

        date_patterns = [
            ("%d/%m/%Y %H:%M:%S", False),
            ("%d/%m/%Y %H:%M", False),
            ("%d/%m/%Y", False),
            ("%Y-%m-%d %H:%M:%S", False),
            ("%Y-%m-%d %H:%M", False),
            ("%d/%m %H:%M", True),
        ]
        for pattern, needs_year in date_patterns:
            try:
                parsed = datetime.strptime(dt_raw.strip(), pattern)
                if needs_year:
                    parsed = parsed.replace(year=now.year)
                return parsed
            except Exception:
                continue

        return now

    @staticmethod
    def parse_duration_to_seconds(dur_str: str) -> int:
        """Convert duration string (e.g. '35m 12s', '1 minuto 44 segundos', '1h 10m', '00:25:30') into seconds."""
        if not dur_str:
            return 900  # Default 15 minutes

        clean = dur_str.strip().lower()

        # Handle HH:MM:SS or MM:SS
        if ":" in clean:
            parts = clean.split(":")
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = int(parts[0]), int(parts[1])
                return m * 60 + s

        # Handle "1 hora 12 minutos 5 segundos" or "1h 30m 15s" or "45m"
        hours = 0
        minutes = 0
        seconds = 0
        h_match = re.search(r"(\d+)\s*(?:hora|horas|h)", clean)
        m_match = re.search(r"(\d+)\s*(?:minuto|minutos|min|m)", clean)
        s_match = re.search(r"(\d+)\s*(?:segundo|segundos|s)", clean)

        if h_match:
            hours = int(h_match.group(1))
        if m_match:
            minutes = int(m_match.group(1))
        if s_match:
            seconds = int(s_match.group(1))

        total = hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else 60

    @classmethod
    def format_seconds_to_duration(cls, seconds: int) -> str:
        """Format seconds into readable Portuguese string (e.g. '1h 15m' or '25m')."""
        if seconds <= 0:
            return "15m"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 and hours == 0:
            parts.append(f"{secs}s")

        return " ".join(parts) if parts else "1m"

    @classmethod
    def import_teams_calls(cls, db: Session, raw_calls: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Import or update Teams calls in PostgreSQL with deduplication.

        Returns:
            Tuple of (created_count, updated_count)
        """
        created = 0
        updated = 0

        logger.info(f"[TEAMS IMPORT] Recebendo {len(raw_calls)} chamadas para importação...")

        for call in raw_calls:
            contact = (call.get("contact_name") or call.get("name") or "Colega TJCE").strip()
            call_type = (call.get("call_type") or call.get("type") or "efetuada").strip().lower()
            dur_str = (call.get("duration") or "15m").strip()
            title = (call.get("title") or f"Alinhamento com {contact}").strip()
            raw_time = call.get("date_str") or call.get("start_time") or call.get("timestamp")

            start_dt = cls.parse_datetime_flexible(raw_time)
            dur_secs = cls.parse_duration_to_seconds(dur_str)
            end_dt = start_dt + timedelta(seconds=dur_secs)
            formatted_dur = cls.format_seconds_to_duration(dur_secs)

            # Deduplication: look for meeting with same contact and within 15 minutes of start_time
            window_start = start_dt - timedelta(minutes=15)
            window_end = start_dt + timedelta(minutes=15)

            stmt = select(Meeting).where(
                and_(
                    Meeting.contact_name == contact,
                    Meeting.start_time >= window_start,
                    Meeting.start_time <= window_end,
                )
            )
            existing = db.execute(stmt).scalars().first()

            if existing:
                # Update duration if newly scraped has more precision
                existing.duration = formatted_dur
                existing.end_time = end_dt
                if call_type:
                    existing.call_type = call_type
                updated += 1
            else:
                new_meeting = Meeting(
                    title=title,
                    contact_name=contact,
                    call_type=call_type,
                    start_time=start_dt,
                    end_time=end_dt,
                    duration=formatted_dur,
                    status="pendente",
                )
                db.add(new_meeting)
                created += 1

        db.commit()
        logger.info(f"[TEAMS IMPORT] Importação finalizada: {created} novas chamadas salvas, {updated} atualizadas.")
        return created, updated

    @classmethod
    def get_meetings(
        cls,
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Meeting]:
        """Fetch stored meetings with optional filtering."""
        stmt = select(Meeting)

        conditions = []
        if start_date:
            conditions.append(Meeting.start_time >= start_date)
        if end_date:
            conditions.append(Meeting.start_time <= end_date)
        if search:
            q = f"%{search.strip()}%"
            conditions.append(or_(Meeting.title.ilike(q), Meeting.contact_name.ilike(q)))
        if status:
            conditions.append(Meeting.status == status)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(desc(Meeting.start_time))
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def build_ic_description_for_meetings(cls, meetings: List[Meeting], title: str) -> str:
        """Build formal Redmine catalog item evidence description from meeting records."""
        total_seconds = sum(cls.parse_duration_to_seconds(m.duration) for m in meetings)
        total_dur_str = cls.format_seconds_to_duration(total_seconds)

        lines = [
            f"Atividade: {title}",
            f"Total de Reuniões / Chamadas: {len(meetings)}",
            f"Duração Total Acumulada: {total_dur_str}",
            "",
            "Detalhamento das Chamadas Realizadas (Evidência Microsoft Teams):",
            "| Data e Horário | Contato / Participante | Tipo | Duração |",
            "|---|---|---|---|",
        ]

        for m in sorted(meetings, key=lambda x: x.start_time):
            dt_str = m.start_time.strftime("%d/%m/%Y %H:%M")
            contact = m.contact_name or m.title
            call_type = (m.call_type or "Reunião").capitalize()
            lines.append(f"| {dt_str} | {contact} | {call_type} | {m.duration} |")

        lines.append("")
        lines.append("Nota: Levantamento e auditoria gerados automaticamente via Productivity Assistant.")
        return "\n".join(lines)

    @classmethod
    def create_ic_for_meetings(
        cls,
        db: Session,
        meeting_ids: List[int],
        title: str,
        activity_type: Optional[str] = None,
        complexity: str = "Baixa",
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[int], List[str]]:
        """Create a Redmine Catalog Item for one or multiple meetings."""
        if not meeting_ids:
            return False, None, None, ["Nenhuma reunião selecionada para criação de IC."]

        stmt = select(Meeting).where(Meeting.id.in_(meeting_ids))
        meetings = list(db.execute(stmt).scalars().all())

        if not meetings:
            return False, None, None, ["Reuniões não encontradas no banco de dados."]

        act_type = activity_type or cls.DEFAULT_ACTIVITY_TYPE
        desc = cls.build_ic_description_for_meetings(meetings, title)
        ic_count = len(meetings)

        # Call Redmine Service
        success, issue_url, issue_id, logs = RedmineService.create_catalog_item_api(
            title=title,
            description=desc,
            ic_count=ic_count,
            activity_type=act_type,
            complexity=complexity,
            dry_run=dry_run,
        )

        # If official creation succeeded, update meetings status
        if success and not dry_run and issue_id:
            for m in meetings:
                m.status = "criado"
                m.redmine_id = str(issue_id)
            db.commit()
            logger.info(f"[MEETING IC] {len(meetings)} reuniões vinculadas à tarefa Redmine #{issue_id}.")

        return success, issue_url, issue_id, logs

