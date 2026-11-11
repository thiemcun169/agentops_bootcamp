"""Sessions: one conversation each, owned by the user of the token."""
import logging

from fastapi import APIRouter

from research_assistant.agent.events import session_messages
from research_assistant.api.deps import Agent, CurrentUser, OwnedSession, Sessions
from research_assistant.schemas import Session, SessionDetail

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


@router.post("", status_code=201)
async def create_session(user_id: CurrentUser, sessions: Sessions) -> Session:
    session = await sessions.create(user_id)
    logger.info("session created: %s", session.session_id)
    return session


@router.get("")
async def list_sessions(user_id: CurrentUser, sessions: Sessions) -> list[Session]:
    return await sessions.list(user_id)


@router.get("/{session_id}")
async def get_session(session: OwnedSession, agent: Agent) -> SessionDetail:
    return SessionDetail(**session.model_dump(), messages=await session_messages(agent, session.session_id))
