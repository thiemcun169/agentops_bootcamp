# Langfuse code evaluator (Evaluators → New evaluator → Code evaluator → Python): paste this file.
# Runs inside Langfuse on each matched observation: standard library only, no network, at most 2 seconds.
# Same rule as cites_sources in src/research_assistant/evaluators.py.
# https://langfuse.com/docs/evaluation/evaluation-methods/code-evaluators
import json
import re


def evaluate(ctx: EvaluationContext) -> EvaluationResult:
    output = ctx.observation.output
    output = json.loads(output) if isinstance(output, str) else (output or {})
    answer = output.get("answer", "")
    tail = answer.split("Sources:", 1)
    ok = len(tail) == 2 and re.search(r"https?://\S+", tail[1]) is not None
    return EvaluationResult(scores=[Score(
        name="cites_sources", value=ok, data_type="BOOLEAN",
        comment="Sources line with a URL" if ok else "no Sources: line with a URL")])
