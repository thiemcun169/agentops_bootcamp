"""Runs: send one message to the agent and receive the run as Server-Sent Events (text/event-stream)."""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterable

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from research_assistant.agent.events import short, stream_run
from research_assistant.api.deps import Agent, OwnedSession, Sessions, SettingsDep
from research_assistant.api.errors import problem, run_failure
from research_assistant.schemas import RunRequest

router = APIRouter(prefix="/sessions", tags=["runs"])
logger = logging.getLogger(__name__)


@router.post("/{session_id}/runs", response_class=EventSourceResponse)
async def create_run(body: RunRequest, session: OwnedSession, agent: Agent, sessions: Sessions,
                     settings: SettingsDep, request: Request) -> AsyncIterable[ServerSentEvent]:
    """Run the agent on this session. Every check above (token, owner, body) passes before the first byte is sent."""
    run_id, seq, started = uuid.uuid4().hex[:8], 0, time.monotonic()

    def event(name: str, data: dict) -> ServerSentEvent:
        nonlocal seq
        seq += 1
        return ServerSentEvent(event=name, data=data, id=f"{run_id}-{seq}")

    if session.title == "New session":
        sessions.rename(session, short(body.message, 60))
    logger.info("run %s started: message_chars=%d", run_id, len(body.message))  # the text itself is not logged
    yield event("metadata", {"run_id": run_id, "session_id": session.session_id})
    stream = stream_run(agent, body.message, session.session_id)
    try:
        while True:
            try:  # the deadline covers the whole run, not each event
                name, data = await asyncio.wait_for(anext(stream), settings.run_timeout_s - (time.monotonic() - started))
            except StopAsyncIteration:
                break
            if await request.is_disconnected():  # the user closed the tab: stop paying for model and tool calls
                logger.warning("run %s cancelled: client disconnected after %.1f s", run_id, time.monotonic() - started)
                return
            if name == "done":
                logger.info("run %s completed in %.1f s: model_calls=%d input_tokens=%d output_tokens=%d", run_id,
                            data["seconds"], data["model_calls"], data["input_tokens"], data["output_tokens"])
            yield event(name, data)
    except asyncio.CancelledError:
        logger.warning("run %s cancelled after %.1f s", run_id, time.monotonic() - started)
        raise
    except Exception as exc:  # status 200 went out with the first byte: report the failure as an event
        status, detail = run_failure(exc)
        logger.error("run %s failed: %s %r", run_id, status, exc)
        yield event("error", problem(status, detail, request.url.path))
    finally:
        await stream.aclose()
