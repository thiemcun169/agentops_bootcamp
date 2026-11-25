"""Score yesterday's production runs with the same code checks as the gate, and send the scores to Langfuse.
Run it on a schedule (cron, Cloud Scheduler, a scheduled GitHub Actions workflow). Langfuse's own code evaluators
run inside Langfuse with the standard library only; this script can use any package.

    uv run python evals/score_production.py [--hours 24]
https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

from langfuse import EvaluatorInputs, get_client

from research_assistant.core.config import get_settings
from research_assistant.core.langfuse import init_langfuse
from research_assistant.evaluators import at_most_3_bullets, cites_sources, searched_web

parser = argparse.ArgumentParser()
parser.add_argument("--hours", type=int, default=24)
args = parser.parse_args()
since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

# Production traffic has no expected output: every factual answer should search and cite.
PRODUCTION_RULES = {"must_search": True, "must_cite": True}


def mapper(*, item, **kwargs) -> EvaluatorInputs:
    output = json.loads(item.output) if item.output else {"answer": "", "tools": []}  # a failed run has no output
    return EvaluatorInputs(input=json.loads(item.input), output=output, expected_output=PRODUCTION_RULES)


# The scores belong to production traces: create them in the production environment.
init_langfuse(get_settings().model_copy(update={"langfuse_tracing_environment": "production"}))
langfuse = get_client()
result = langfuse.run_batched_evaluation(
    mapper=mapper, evaluators=[cites_sources, searched_web, at_most_3_bullets],
    filter=json.dumps([
        {"type": "string", "column": "name", "operator": "=", "value": "agent-run"},  # the logical root only
        {"type": "stringOptions", "column": "environment", "operator": "any of", "value": ["production"]},
        {"type": "datetime", "column": "startTime", "operator": ">=", "value": since},
    ]))
langfuse.flush()
print(result)
