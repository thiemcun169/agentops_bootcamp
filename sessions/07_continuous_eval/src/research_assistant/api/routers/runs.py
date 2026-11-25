"""Runs: send one message to the agent and receive the run as Server-Sent Events (text/event-stream).

Session 07: every run is one Langfuse trace. Its root observation `agent-run` holds the question and the final
answer (what the online evaluators read), and the user's thumbs up/down is a score on the same trace.
"""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

from research_assistant.agent.events import short, stream_run
from research_assistant.api.deps import Agent, OwnedSession, Sessions, SettingsDep
from research_assistant.api.errors import problem, run_failure
from research_assistant.schemas import Feedback, FeedbackSaved, RunRequest

router = APIRouter(prefix="/sessions", tags=["runs"])
logger = logging.getLogger(__name__)


def run_trace_id(session_id: str, run_id: str) -> str:
    """Same seed, same id: the feedback route finds a run's trace without storing anything."""
    return Langfuse.create_trace_id(seed=f"{session_id}:{run_id}")


@router.post("/{session_id}/runs", response_class=EventSourceResponse)
async def create_run(body: RunRequest, session: OwnedSession, agent: Agent, sessions: Sessions,
                     settings: SettingsDep, request: Request) -> AsyncIterable[ServerSentEvent]:
    """Run the agent on this session. Every check above (token, owner, body) passes before the first byte is sent."""
    run_id, seq, started = uuid.uuid4().hex[:8], 0, time.monotonic()
    trace_id = run_trace_id(session.session_id, run_id)

    def event(name: str, data: dict) -> ServerSentEvent:
        nonlocal seq
        seq += 1
        return ServerSentEvent(event=name, data=data, id=f"{run_id}-{seq}")

    if session.title == "New session":
        await sessions.rename(session, short(body.message, 60))
    logger.info("run %s started: message_chars=%d trace_id=%s", run_id, len(body.message), trace_id)
    yield event("metadata", {"run_id": run_id, "session_id": session.session_id, "trace_id": trace_id})

    # Root observation of the trace + attributes copied to every child (model calls, tool calls).
    with get_client().start_as_current_observation(
            as_type="agent", name="agent-run", trace_context={"trace_id": trace_id},
            input={"question": body.message}) as root, propagate_attributes(
            user_id=request.state.user_id, session_id=session.session_id, trace_name="agent-run",
            version=request.app.state.info.version, prompt=request.app.state.prompt):
        stream = stream_run(agent, body.message, session.session_id, callbacks=[CallbackHandler()])
        try:
            while True:
                try:  # the deadline covers the whole run, not each event
                    name, data = await asyncio.wait_for(anext(stream),
                                                        settings.run_timeout_s - (time.monotonic() - started))
                except StopAsyncIteration:
                    break
                if await request.is_disconnected():  # the user closed the tab: stop paying for model and tool calls
                    logger.warning("run %s cancelled: client disconnected after %.1f s", run_id,
                                   time.monotonic() - started)
                    root.update(level="WARNING", status_message="client disconnected")
                    return
                if name == "done":
                    logger.info("run %s completed in %.1f s: model_calls=%d input_tokens=%d output_tokens=%d", run_id,
                                data["seconds"], data["model_calls"], data["input_tokens"], data["output_tokens"])
                    # What the evaluators need, on the root: the answer and which tools the agent called.
                    root.update(output={"answer": data["answer"], "tools": data["tools"]})
                yield event(name, data)
        except asyncio.CancelledError:
            logger.warning("run %s cancelled after %.1f s", run_id, time.monotonic() - started)
            root.update(level="WARNING", status_message="cancelled")
            raise
        except Exception as exc:  # status 200 went out with the first byte: report the failure as an event
            status, detail = run_failure(exc)
            logger.error("run %s failed: %s %r", run_id, status, exc)
            root.update(level="ERROR", status_message=f"{status} {detail}")
            yield event("error", problem(status, detail, request.url.path))
        finally:
            await stream.aclose()


@router.post("/{session_id}/runs/{run_id}/feedback", status_code=202)
async def send_feedback(body: Feedback, session: OwnedSession,
                        run_id: Annotated[str, Path(pattern=r"^[0-9a-f]{8}$")]) -> FeedbackSaved:
    """Thumbs up (true) or down (false) on one run of the caller's own session, stored as a Langfuse score."""
    trace_id = run_trace_id(session.session_id, run_id)
    # score_id: a second click on the same run replaces the first score instead of adding one.
    get_client().create_score(trace_id=trace_id, score_id=f"{trace_id}-user-feedback", name="user-feedback",
                              value=1 if body.value else 0, data_type="BOOLEAN", comment=body.comment)
    logger.info("feedback on run %s: %s", run_id, "up" if body.value else "down")
    return FeedbackSaved(trace_id=trace_id, name="user-feedback", value=body.value)
