"""Who owns which session. Two stores with the same async methods, chosen by CHECKPOINTER:

- MemorySessionStore: a dict in the process (Session 02). Lost on restart; fine for tests and `fastapi dev`.
- PostgresSessionStore: a `sessions` table next to the checkpointer's tables, so a session and its conversation
  survive `docker compose down` + `up` together.
"""
import uuid
from datetime import datetime, timezone

from psycopg_pool import AsyncConnectionPool

from research_assistant.schemas import Session


def new_session(title: str) -> Session:
    return Session(session_id=str(uuid.uuid4()), title=title, created_at=datetime.now(timezone.utc))


class MemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, Session]] = {}  # session_id -> (owner user_id, session)

    async def setup(self) -> None:
        pass

    async def create(self, user_id: str, title: str = "New session") -> Session:
        session = new_session(title)
        self._sessions[session.session_id] = (user_id, session)
        return session

    async def get(self, user_id: str, session_id: str) -> Session | None:
        """None for "does not exist" AND for "belongs to someone else": callers cannot tell the two apart."""
        owner, session = self._sessions.get(session_id, (None, None))
        return session if owner == user_id else None

    async def list(self, user_id: str) -> list[Session]:
        return [s for owner, s in self._sessions.values() if owner == user_id]

    async def rename(self, session: Session, title: str) -> None:
        session.title = title


class PostgresSessionStore:
    """Same contract as MemorySessionStore; every query filters on user_id, so ownership is enforced in SQL."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool  # the connection pool shared with AsyncPostgresSaver

    async def setup(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id  uuid PRIMARY KEY,
                    user_id     text NOT NULL,
                    title       text NOT NULL,
                    created_at  timestamptz NOT NULL
                )""")
            await conn.execute("CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions (user_id, created_at)")

    async def create(self, user_id: str, title: str = "New session") -> Session:
        session = new_session(title)
        async with self.pool.connection() as conn:
            await conn.execute("INSERT INTO sessions VALUES (%s, %s, %s, %s)",
                               (session.session_id, user_id, session.title, session.created_at))
        return session

    async def get(self, user_id: str, session_id: str) -> Session | None:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT session_id::text, title, created_at FROM sessions "
                                     "WHERE session_id = %s AND user_id = %s", (session_id, user_id))
            row = await cur.fetchone()
        return Session(**row) if row else None

    async def list(self, user_id: str) -> list[Session]:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT session_id::text, title, created_at FROM sessions "
                                     "WHERE user_id = %s ORDER BY created_at", (user_id,))
            return [Session(**row) for row in await cur.fetchall()]

    async def rename(self, session: Session, title: str) -> None:
        session.title = title
        async with self.pool.connection() as conn:
            await conn.execute("UPDATE sessions SET title = %s WHERE session_id = %s", (title, session.session_id))


SessionStore = MemorySessionStore | PostgresSessionStore
