"""Code evaluators: deterministic checks of one run, used offline (eval gate) and online (production traces).

Each check reads the run's output ({"answer": ..., "tools": [...]}) and the case's expectations, and returns a
Langfuse `Evaluation` (a score). They encode the rules of the system prompt that code can check; whether the
answer is right needs a judge or a person (online evaluator, user feedback).
https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk
"""
import re

from langfuse import Evaluation

URL = re.compile(r"https?://\S+")
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _bool(name: str, ok: bool, comment: str) -> Evaluation:
    return Evaluation(name=name, value=1 if ok else 0, data_type="BOOLEAN", comment=comment)


def cites_sources(*, output: dict, expected_output: dict | None = None, **kwargs) -> Evaluation | None:
    """A "Sources:" line with at least one URL (required when the case says must_cite)."""
    if not (expected_output or {}).get("must_cite"):
        return None
    tail = output["answer"].split("Sources:", 1)
    ok = len(tail) == 2 and bool(URL.search(tail[1]))
    return _bool("cites_sources", ok, "Sources line with a URL" if ok else "no Sources: line with a URL")


def searched_web(*, output: dict, expected_output: dict | None = None, **kwargs) -> Evaluation | None:
    """The agent called web_search before stating a number (must_search)."""
    if not (expected_output or {}).get("must_search"):
        return None
    ok = "web_search" in output["tools"]
    return _bool("searched_web", ok, f"tools called: {output['tools'] or 'none'}")


def used_calculator(*, output: dict, expected_output: dict | None = None, **kwargs) -> Evaluation | None:
    """The agent did the arithmetic with the calculate tool, not in its head (must_calculate)."""
    if not (expected_output or {}).get("must_calculate"):
        return None
    ok = "calculate" in output["tools"]
    return _bool("used_calculator", ok, f"tools called: {output['tools'] or 'none'}")


def at_most_3_bullets(*, output: dict, **kwargs) -> Evaluation:
    """The prompt asks for at most 3 bullet points (every case)."""
    n = sum(1 for line in output["answer"].splitlines() if BULLET.match(line))
    return _bool("at_most_3_bullets", n <= 3, f"{n} bullet lines")


CHECKS = [cites_sources, searched_web, used_calculator, at_most_3_bullets]


def case_passed(*, output: dict, expected_output: dict | None = None, **kwargs) -> Evaluation:
    """One verdict per case: every check that applies passed. The gate compares this value with the baseline."""
    results = [r for check in CHECKS if (r := check(output=output, expected_output=expected_output))]
    failed = [r.name for r in results if r.value == 0]
    return _bool("case_passed", not failed, "failed: " + ", ".join(failed) if failed else "all checks passed")


def pass_rate(*, item_results, **kwargs) -> Evaluation:
    """Run evaluator: share of cases whose case_passed is 1."""
    values = [e.value for r in item_results for e in r.evaluations if e.name == "case_passed"]
    rate = sum(values) / len(values) if values else 0.0
    return Evaluation(name="pass_rate", value=round(rate, 3), comment=f"{sum(values)}/{len(values)} cases passed")
