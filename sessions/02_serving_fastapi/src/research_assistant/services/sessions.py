"""Who owns which session. Kept in process memory: serve with ONE worker process (a database replaces this later)."""
import uuid
from datetime import datetime, timezone

from research_assistant.schemas import SessionRecord


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, user_id: str, title: str = "New session") -> SessionRecord:
        record = SessionRecord(session_id=str(uuid.uuid4()), title=title,
                               created_at=datetime.now(timezone.utc), user_id=user_id)
        self._sessions[record.session_id] = record
        return record

    def get(self, user_id: str, session_id: str) -> SessionRecord | None:
        """None for "does not exist" AND for "belongs to someone else": callers cannot tell the two apart."""
        record = self._sessions.get(session_id)
        return record if record and record.user_id == user_id else None

    def list(self, user_id: str) -> list[SessionRecord]:
        return [r for r in self._sessions.values() if r.user_id == user_id]

    def rename(self, record: SessionRecord, title: str) -> None:
        record.title = title

    def __len__(self) -> int:
        return len(self._sessions)
