"""Turn one production trace into a regression case: its question, the search results the agent saw, and the
criteria you pass on the command line. The item keeps a link to the trace (source_trace_id).

    uv run python evals/add_from_trace.py <trace_id> --must-search --must-cite
"""
import argparse
import json

from langfuse import get_client

from research_assistant.core.config import get_settings
from research_assistant.core.langfuse import init_langfuse

DATASET = "research-assistant-regression"

parser = argparse.ArgumentParser()
parser.add_argument("trace_id")
for flag in ("must-search", "must-cite", "must-calculate"):
    parser.add_argument(f"--{flag}", action="store_true")
args = parser.parse_args()

init_langfuse(get_settings())
langfuse = get_client()
observations = [o for page in langfuse.iter_observation_pages(trace_id=args.trace_id, fields="core,basic,io")
                for o in page.data]
root = next(o for o in observations if o.name == "agent-run")
seen = {}
for o in observations:  # every web_search result the agent read in this run, once per URL
    if o.type == "TOOL" and o.name == "web_search":
        content = json.loads(o.output)["content"] if isinstance(o.output, str) else o.output["content"]
        for r in json.loads(content) if isinstance(content, str) else content:
            seen.setdefault(r["url"], r)
expected = {k.replace("-", "_"): True for k in ("must-search", "must-cite", "must-calculate")
            if getattr(args, k.replace("-", "_"))}
item_id = f"prod-{args.trace_id[:8]}"
langfuse.create_dataset_item(dataset_name=DATASET, id=item_id, input=json.loads(root.input),
                             expected_output=expected, source_trace_id=args.trace_id, source_observation_id=root.id,
                             metadata={"origin": "production", "search_results": list(seen.values())[:6]})
langfuse.flush()
print(f"+ {item_id}: {json.loads(root.input)['question']!r} expected={expected} search_results={len(seen)}")
