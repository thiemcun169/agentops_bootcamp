"""Liveness (/health: the process answers) and readiness (/ready: it can serve a run now).
No token and no /v1 prefix: a load balancer or the platform calls them. Neither calls the model."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def database_check(pool) -> str:
    try:
        async with pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
        return "ok"
    except Exception as exc:  # the process is alive (/health 200) but cannot serve a run
        logger.warning("database check failed: %r", exc)
        return "unreachable"


@router.get("/ready", responses={503: {"description": "Not ready: do not send traffic yet"}})
async def ready(request: Request):
    state = request.app.state
    checks = {
        "agent": "ok" if getattr(state, "agent", None) is not None else "missing",
        "sessions": "ok" if getattr(state, "sessions", None) is not None else "missing",
        "accepting": "ok" if getattr(state, "accepting", False) else "draining",
    }
    if getattr(state, "pool", None) is not None:  # CHECKPOINTER=postgres: can we reach the database now?
        checks["database"] = await database_check(state.pool)
    if all(v == "ok" for v in checks.values()):
        return {"status": "ready", "checks": checks}
    logger.warning("not ready: %s", checks)
    return JSONResponse({"status": "not ready", "checks": checks}, 503)
