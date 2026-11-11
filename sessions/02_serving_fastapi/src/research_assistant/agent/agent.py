"""Build the agent (same model, tools and prompt as Session 01) and run one question from the command line."""
import hashlib
import time

import openai
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from research_assistant.agent.tools import calculate, web_search
from research_assistant.core.config import Settings

PROMPT_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"


def load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").strip()


def prompt_sha256() -> str:
    """Session 01 versions the prompt by the hash of its file (the baseline manifest stores the same value)."""
    return hashlib.sha256(PROMPT_FILE.read_bytes()).hexdigest()[:12]


async def check_model(settings: Settings) -> bool:
    """Can the provider serve our model with our key? A metadata call: no tokens, no cost."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(), timeout=3, max_retries=0)  # a probe must answer fast
    try:
        await client.models.retrieve(settings.model.split(":", 1)[-1])  # "openai:gpt-6-luna" -> "gpt-6-luna"
        return True
    except openai.APIError:  # bad or revoked key (401), unknown model (404), provider down
        return False
    finally:
        await client.close()


def build_agent(settings: Settings, checkpointer: BaseCheckpointSaver | None = None):
    """With a checkpointer, the agent keeps each conversation under its thread_id (the API's session_id)."""
    model = init_chat_model(settings.model, api_key=settings.openai_api_key.get_secret_value())
    return create_agent(model=model, tools=[web_search, calculate], system_prompt=load_prompt(),
                        checkpointer=checkpointer)


def ask(question: str, settings: Settings) -> dict:
    """Session 01 CLI path: one blocking run, then the answer with tokens and cost from the provider's metadata."""
    started = time.monotonic()
    result = build_agent(settings).invoke({"messages": [{"role": "user", "content": question}]})
    latency_s = time.monotonic() - started

    ai = [m for m in result["messages"] if isinstance(m, AIMessage)]
    tools = [m.name for m in result["messages"] if isinstance(m, ToolMessage)]
    input_tokens = sum((m.usage_metadata or {}).get("input_tokens", 0) for m in ai)
    output_tokens = sum((m.usage_metadata or {}).get("output_tokens", 0) for m in ai)
    cost = (input_tokens * settings.price_input_per_mtok + output_tokens * settings.price_output_per_mtok) / 1e6
    return {
        "answer": ai[-1].text,
        "served_model": ai[-1].response_metadata.get("model_name"),
        "metrics": {
            "latency_s": round(latency_s, 1),
            "model_calls": len(ai),
            "tool_calls": tools,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 5),
        },
    }
