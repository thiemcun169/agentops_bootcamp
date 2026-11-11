"""The FastAPI application: start-up and shutdown (lifespan), middleware, error handlers, routers and the demo UI.

Run:  uv run fastapi dev      development: auto-reload, binds 127.0.0.1
      uv run fastapi run      serving: no reload, binds 0.0.0.0 (entrypoint set in pyproject.toml)
"""
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import InMemorySaver

from research_assistant.agent.agent import build_agent, prompt_sha256
from research_assistant.api.deps import get_current_user
from research_assistant.api.errors import add_error_handlers, problem_response
from research_assistant.api.routers import health, info, runs, sessions
from research_assistant.core.config import PROJECT_DIR, get_settings
from research_assistant.core.logging import request_id_var, setup_logging, user_id_var
from research_assistant.schemas import Info
from research_assistant.services.sessions import SessionStore

logger = logging.getLogger("research_assistant.api")
settings = get_settings()  # read once at import: the middleware below needs the CORS origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once: everything before `yield` at start-up, everything after it at shutdown."""
    setup_logging(settings.log_level)
    started = time.perf_counter()
    app.state.agent = build_agent(settings, InMemorySaver())  # one model client and graph for every request
    app.state.sessions = SessionStore()
    app.state.info = Info(service="research-assistant", version=version("research-assistant"),
                          app_env=settings.app_env, model=settings.model, prompt_sha256=prompt_sha256())
    logger.info("agent ready in %.0f ms: model=%s prompt_sha256=%s", (time.perf_counter() - started) * 1000,
                settings.model, app.state.info.prompt_sha256)
    yield
    logger.info("shutdown: %d sessions dropped (kept in memory)", len(app.state.sessions))


app = FastAPI(title="Research Assistant API", version=version("research-assistant"), lifespan=lifespan,
              description="The research agent as an HTTP service: one session per conversation, each run streamed "
                          "as Server-Sent Events.")

REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # a client-sent id is reused only if it is safe to log


def request_id_from(request: Request) -> str:
    incoming = request.headers.get("x-request-id", "")
    return incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex[:12]


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Give every request an id (header X-Request-ID), time it, and log one line when the response starts."""
    request_id = request_id_from(request)
    request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # a bug: full traceback in the log, a short problem body (no stack trace) for the client
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        response = problem_response(500, "Unexpected error. Quote the request_id when reporting it.",
                                    request.url.path)
    ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    user_id_var.set(getattr(request.state, "user_id", "-"))  # set by get_current_user, if the route needed a token
    logger.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


# Added last = runs first: a browser's preflight (OPTIONS) is answered before the request_id middleware.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID"])
add_error_handlers(app)

auth = [Depends(get_current_user)]  # every /v1 route needs a token
api_v1 = APIRouter(prefix="/v1", dependencies=auth)
api_v1.include_router(info.router)
api_v1.include_router(sessions.router)
api_v1.include_router(runs.router)
app.include_router(api_v1)
app.include_router(health.router)
app.mount("/ui", StaticFiles(directory=PROJECT_DIR / "static", html=True), name="ui")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/ui/")
