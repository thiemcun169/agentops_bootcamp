"""Create the regression dataset on Langfuse from evals/cases.jsonl (safe to run again: items are upserted by id).

Each case gets the web search results of its question, recorded once and stored in the item's metadata.
The gate replays them instead of calling Tavily, so a red build means the agent changed, not the web.

    uv run python evals/upload_dataset.py
"""
import json
from pathlib import Path

from langfuse import get_client
from tavily import TavilyClient

from research_assistant.core.config import get_settings
from research_assistant.core.langfuse import init_langfuse

DATASET = "research-assistant-regression"
CASES = Path(__file__).with_name("cases.jsonl")

settings = get_settings()
init_langfuse(settings)
langfuse = get_client()
tavily = TavilyClient(api_key=settings.tavily_api_key.get_secret_value())

langfuse.create_dataset(name=DATASET, description="Regression cases of the research assistant: one item per "
                        "behaviour the system prompt promises, plus failures found in production.")
existing = {item.id for item in langfuse.get_dataset(DATASET).items}
for line in CASES.read_text(encoding="utf-8").splitlines():
    case = json.loads(line)
    if case["id"] in existing:
        print(f"= {case['id']} (already in the dataset)")
        continue
    results = tavily.search(case["question"], max_results=settings.max_search_results)["results"]
    langfuse.create_dataset_item(
        dataset_name=DATASET, id=case["id"], input={"question": case["question"]},
        expected_output=case["expected"],  # criteria, not a reference text: two good answers never match word for word
        metadata={"origin": "designed", "search_results": [
            {"title": r["title"], "url": r["url"], "content": r["content"][:500]} for r in results]})
    print(f"+ {case['id']}")
langfuse.flush()
print(f"dataset {DATASET}: {len(langfuse.get_dataset(DATASET).items)} items")
