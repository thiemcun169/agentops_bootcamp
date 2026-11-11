"""Sessions: one conversation each, owned by the user of the token."""
import logging
from typing import Annotated

from fastapi import APIRouter, Query

from research_assistant.agent.events import session_messages
from research_assistant.api.deps import Agent, CurrentUser, OwnedSession, Sessions
from research_assistant.schemas import Session, SessionDetail

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


@router.post("", status_code=201)
async def create_session(user_id: CurrentUser, sessions: Sessions) -> Session:
    session = sessions.create(user_id)
    logger.info("session created: %s", session.session_id)
    return session


@router.get("")
async def list_sessions(user_id: CurrentUser, sessions: Sessions,
                        limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[Session]:
    """limit is a query parameter (?limit=5): a plain type that is not in the path."""
    return sessions.list(user_id)[-limit:]


@router.get("/{session_id}")
async def get_session(session: OwnedSession, agent: Agent) -> SessionDetail:
    return SessionDetail(**session.model_dump(exclude={"user_id"}),
                         messages=await session_messages(agent, session.session_id))
