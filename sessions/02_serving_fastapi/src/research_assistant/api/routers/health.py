"""Liveness (/health: the process answers) and readiness (/ready: a run can succeed now).
No token and no /v1 prefix: a load balancer or the platform calls them. Neither calls the model with tokens."""
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from research_assistant.agent.agent import check_model
from research_assistant.api.deps import SettingsDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)
_model_check = {"at": 0.0, "ok": False}


async def model_ready(settings: SettingsDep) -> bool:
    """Provider check, cached 30 s so a probe every few seconds does not call the provider every time."""
    if time.monotonic() - _model_check["at"] > 30:
        _model_check.update(at=time.monotonic(), ok=await check_model(settings))
    return _model_check["ok"]


ModelReady = Annotated[bool, Depends(model_ready)]


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", responses={503: {"description": "Not ready: send no traffic"}})
async def ready(request: Request, model_ok: ModelReady):
    checks = {
      "agent": hasattr(request.app.state,
                       "agent"),
      "model": model_ok}
    if all(checks.values()):
        return {"status": "ready",
                "checks": checks}
    logger.warning("not ready: %s", checks)
    return JSONResponse({"status":
        "not ready", "checks": checks}, 503)
