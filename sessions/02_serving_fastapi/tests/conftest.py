"""Offline API tests: no API key, no network, no model call.

Placeholder keys let Settings load (a real environment variable wins over .env, so the real keys are never used);
the real agent is replaced by FakeAgent through app.dependency_overrides.
"""
import os

os.environ.update(OPENAI_API_KEY="test-key", TAVILY_API_KEY="test-key", CORS_ORIGINS="[]")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage  # noqa: E402

from research_assistant.api.deps import get_agent  # noqa: E402
from research_assistant.api.main import app  # noqa: E402

ALICE = {"Authorization": "Bearer alice-dev-token"}
BOB = {"Authorization": "Bearer bob-dev-token"}


class FakeAgent:
    """Replays the stream shape of the real agent: model asks for a tool, the tool answers, the model answers."""

    def __init__(self):
        self.history: dict[str, list] = {}

    async def astream(self, payload, config, stream_mode):
        call = {"id": "call_1", "name": "calculate", "args": {"expression": "12000 / 2.5"}}
        yield "updates", {"model": {"messages": [AIMessage("", tool_calls=[call],
                                                           usage_metadata={"input_tokens": 500, "output_tokens": 20,
                                                                           "total_tokens": 520})]}}
        yield "updates", {"tools": {"messages": [ToolMessage("4800.0", tool_call_id="call_1", name="calculate")]}}
        for text in ("It needs ", "4,800 kWh."):
            yield "messages", (AIMessageChunk(text), {"langgraph_node": "model"})
        answer = AIMessage("It needs 4,800 kWh.", usage_metadata={"input_tokens": 600, "output_tokens": 10,
                                                                   "total_tokens": 610})
        yield "updates", {"model": {"messages": [answer]}}
        thread = config["configurable"]["thread_id"]
        self.history.setdefault(thread, []).extend([HumanMessage(payload["messages"][0]["content"]), answer])

    async def aget_state(self, config):
        class State:
            values = {"messages": self.history.get(config["configurable"]["thread_id"], [])}
        return State()


@pytest.fixture
def client():
    with TestClient(app) as c:  # `with` runs the lifespan (start-up and shutdown)
        fake = FakeAgent()
        app.dependency_overrides[get_agent] = lambda: fake  # every route now gets the fake, never the real model
        yield c
    app.dependency_overrides.clear()
