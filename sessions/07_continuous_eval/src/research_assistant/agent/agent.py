"""Build the agent (same model and tools as Session 01) with its prompt from Langfuse, and run one question."""
import logging
import time
import tomllib
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langfuse import get_client
from langfuse.model import PromptClient
from langgraph.checkpoint.base import BaseCheckpointSaver

from research_assistant.agent.tools import calculate, web_search
from research_assistant.core.config import Settings

logger = logging.getLogger(__name__)
PROMPT_PIN = Path(__file__).parent / "prompt.toml"
# Used only when Langfuse cannot be reached (or has no keys): same text as version 1, never linked to traces.
FALLBACK_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"


def load_prompt(settings: Settings) -> PromptClient:
    """The pinned prompt version from Langfuse Prompt Management (PROMPT_VERSION overrides the pin)."""
    pin = tomllib.loads(PROMPT_PIN.read_text(encoding="utf-8"))
    prompt = get_client().get_prompt(pin["name"], version=settings.prompt_version or pin["version"],
                                     fallback=FALLBACK_FILE.read_text(encoding="utf-8").strip())
    if prompt.is_fallback:
        logger.warning("prompt %s: Langfuse unreachable or no keys, using the fallback file", pin["name"])
    return prompt


def prompt_label(prompt: PromptClient) -> str:
    return f"{prompt.name} v{prompt.version}" + (" (fallback)" if prompt.is_fallback else "")


def build_agent(settings: Settings, prompt: PromptClient, checkpointer: BaseCheckpointSaver | None = None,
                tools: list | None = None):
    """With a checkpointer, the agent keeps each conversation under its thread_id (the API's session_id).
    `tools` replaces the real tools (the eval gate replays recorded search results)."""
    model = init_chat_model(settings.model, api_key=settings.openai_api_key.get_secret_value())
    return create_agent(model=model, tools=tools or [web_search, calculate], system_prompt=prompt.prompt,
                        checkpointer=checkpointer)


def ask(question: str, settings: Settings) -> dict:
    """Session 01 CLI path: one blocking run, then the answer with tokens and cost from the provider's metadata."""
    started = time.monotonic()
    result = build_agent(settings, load_prompt(settings)).invoke({"messages": [{"role": "user", "content": question}]})
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
