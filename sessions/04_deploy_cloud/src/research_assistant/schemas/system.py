"""Service metadata and the error body."""
from pydantic import BaseModel


class Info(BaseModel):
    """What is running: the release, the configured model snapshot and the prompt version (Session 01 manifest)."""
    service: str
    version: str
    app_env: str
    model: str
    prompt_sha256: str
    revision: str | None = None  # Session 04: the Cloud Run revision serving this request (env K_REVISION)


class Problem(BaseModel):
    """RFC 9457 Problem Details: one error body for every failure (media type application/problem+json)."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    request_id: str  # extension member: quote it to find the request in the logs
