"""The API contract: request and response bodies. FastAPI turns them into the OpenAPI schema shown at /docs."""
from research_assistant.schemas.sessions import Message, RunRequest, Session, SessionDetail, SessionRecord
from research_assistant.schemas.system import Info, Problem

__all__ = ["Info", "Message", "Problem", "RunRequest", "Session", "SessionDetail", "SessionRecord"]
