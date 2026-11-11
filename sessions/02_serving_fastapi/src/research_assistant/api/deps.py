"""Dependencies: settings, the caller's identity, the objects built at start-up, and the session ownership check.

Declared as `Annotated[type, Depends(fn)]` aliases so every route reads the same way and tests can replace any of
them with `app.dependency_overrides[fn] = fake`.
"""
import json
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from research_assistant.core.config import Settings, get_settings
from research_assistant.core.logging import session_id_var, user_id_var
from research_assistant.schemas import SessionRecord
from research_assistant.services.sessions import SessionStore

SettingsDep = Annotated[Settings, Depends(get_settings)]

bearer = HTTPBearer(auto_error=False)  # reads "Authorization: Bearer <token>"; adds the Authorize button to /docs


@lru_cache
def load_tokens(path: str) -> dict[str, str]:
    return json.loads(open(path, encoding="utf-8").read())["tokens"]


async def get_current_user(request: Request, settings: SettingsDep,
                           cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    """The user_id comes from the token, never from the request body."""
    user_id = load_tokens(str(settings.users_file)).get(cred.credentials) if cred else None
    if user_id is None:
        raise HTTPException(401, "Missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
    user_id_var.set(user_id)  # every log line of this request now carries user_id
    request.state.user_id = user_id  # read back by the request_id middleware for its own log line
    return user_id


CurrentUser = Annotated[str, Depends(get_current_user)]


def get_agent(request: Request):
    return request.app.state.agent  # built once in lifespan


def get_sessions(request: Request) -> SessionStore:
    return request.app.state.sessions


Agent = Annotated[object, Depends(get_agent)]
Sessions = Annotated[SessionStore, Depends(get_sessions)]


async def get_owned_session(session_id: UUID, user_id: CurrentUser, sessions: Sessions) -> SessionRecord:
    """session_id is a path parameter typed UUID: "/v1/sessions/abc" is a 422 before this code runs."""
    session = sessions.get(user_id, str(session_id))
    if session is None:  # same answer for "does not exist" and "belongs to someone else"
        raise HTTPException(404, f"Session {session_id} not found")
    session_id_var.set(session.session_id)
    return session


OwnedSession = Annotated[SessionRecord, Depends(get_owned_session)]
