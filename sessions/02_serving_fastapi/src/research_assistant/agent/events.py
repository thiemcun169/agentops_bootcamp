"""Turn the agent's LangGraph stream into a small list of events a user interface understands.

stream_mode "updates" -> step, tool_call, tool_result · "messages" -> token. The caller adds `metadata` first and
ends with `done` (or `error`). Only names, arguments and short previews leave the process: never the full state
(system prompt, raw search results, provider metadata).
"""
import time
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


def short(value, n: int = 160) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= n else text[:n] + "…"


def to_events(mode: str, chunk) -> list[tuple[str, dict]]:
    """One LangGraph stream chunk -> zero or more (event name, data) pairs."""
    if mode == "messages":  # (message chunk, metadata): text tokens of the agent's model node only
        token, meta = chunk
        ok = isinstance(token, AIMessageChunk) and token.text and meta.get("langgraph_node") == "model"
        return [("token", {"text": token.text})] if ok else []
    events = []  # "updates": {node name: what the node returned}
    for node, update in chunk.items():
        if node not in ("model", "tools") or not isinstance(update, dict):
            continue
        events.append(("step", {"node": node}))
        for m in update.get("messages", []):
            for c in getattr(m, "tool_calls", None) or []:
                events.append(("tool_call", {"id": c["id"], "name": c["name"], "args": c["args"]}))
            if isinstance(m, ToolMessage):
                events.append(("tool_result", {"id": m.tool_call_id, "name": m.name, "status": m.status,
                                               "preview": short(m.text)}))
    return events


async def stream_run(agent, message: str, session_id: str) -> AsyncIterator[tuple[str, dict]]:
    """Run the agent on one session and yield its events, then a `done` event with what the run used."""
    started = time.monotonic()
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 20}
    usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0}
    answer = ""
    async for mode, chunk in agent.astream({"messages": [{"role": "user", "content": message}]}, config,
                                           stream_mode=["updates", "messages"]):
        if mode == "updates":
            for m in (chunk.get("model") or {}).get("messages", []):
                if isinstance(m, AIMessage):  # one per model call; tokens reported by the provider
                    usage["model_calls"] += 1
                    usage["input_tokens"] += (m.usage_metadata or {}).get("input_tokens", 0)
                    usage["output_tokens"] += (m.usage_metadata or {}).get("output_tokens", 0)
                    answer = m.text
        for event in to_events(mode, chunk):
            yield event
    yield "done", {"status": "completed", "answer": answer, "seconds": round(time.monotonic() - started, 1), **usage}


async def session_messages(agent, session_id: str) -> list[dict]:
    """The conversation stored by the checkpointer: user questions and agent answers (tool traffic left out)."""
    state = await agent.aget_state({"configurable": {"thread_id": session_id}})
    out = []
    for m in state.values.get("messages", []):
        if m.type == "human":
            out.append({"role": "user", "content": m.text})
        elif isinstance(m, AIMessage) and m.text and not m.tool_calls:
            out.append({"role": "assistant", "content": m.text})
    return out
