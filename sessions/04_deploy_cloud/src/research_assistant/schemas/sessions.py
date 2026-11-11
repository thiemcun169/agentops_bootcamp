"""Sessions and runs. A session is one conversation; a run is one question answered inside it."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # an unknown field such as "user_id" is a 422, not silently ignored
    # min_length: an empty question would still cost a model call; max_length: caps the tokens one request can spend
    message: str = Field(min_length=1, max_length=2000,
                         examples=["What seasonal COP do air-source heat pumps reach in cold climates?"])


class Session(BaseModel):
    session_id: str
    title: str
    created_at: datetime


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionDetail(Session):
    messages: list[Message]
