# Langfuse code evaluator (Evaluators → New evaluator → Code evaluator → Python): paste this file.
# Runs inside Langfuse on each matched observation: standard library only, no network, at most 2 seconds.
# Same rule as cites_sources in src/research_assistant/evaluators.py.
# https://langfuse.com/docs/evaluation/evaluation-methods/code-evaluators
import json
import re


def evaluate(ctx: EvaluationContext) -> EvaluationResult:
    out = ctx.observation.output
    if isinstance(out, str):
        out = json.loads(out)
    tail = (out or {}).get("answer", "").split("Sources:", 1)
    url = r"https?://\S+"
    ok = len(tail) == 2 and re.search(url, tail[1])
    return EvaluationResult(scores=[Score(
        name="cites_sources", value=bool(ok), data_type="BOOLEAN",
        comment="Sources line with a URL" if ok else "no Sources: line with a URL")])
