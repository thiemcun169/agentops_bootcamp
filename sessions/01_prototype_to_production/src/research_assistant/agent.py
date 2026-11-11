"""Build the agent and run one question; return the answer with what the run used and cost."""
import time

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage

from research_assistant.config import Settings, load_prompt
from research_assistant.tools import calculate, web_search


def build_agent(settings: Settings):
    model = init_chat_model(settings.model, api_key=settings.openai_api_key.get_secret_value())
    return create_agent(model=model, tools=[web_search, calculate], system_prompt=load_prompt())


def ask(question: str, settings: Settings) -> dict:
    """Run the agent once. Tokens and the served model ID come from the provider's response metadata."""
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
