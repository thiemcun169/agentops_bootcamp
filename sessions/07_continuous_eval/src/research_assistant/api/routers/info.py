"""What is running: release, model snapshot and prompt version (the Session 01 manifest, served over HTTP)."""
from fastapi import APIRouter, Request

from research_assistant.schemas import Info

router = APIRouter(tags=["info"])


@router.get("/info")
async def info(request: Request) -> Info:
    return request.app.state.info  # computed once at start-up
