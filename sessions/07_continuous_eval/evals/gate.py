"""Eval gate: run the regression dataset on the prompt version of this branch and compare every case with the
approved baseline. A case that passed in the baseline and fails now blocks the merge (RegressionError).

    uv run python evals/gate.py                      # the version pinned in agent/prompt.toml
    PROMPT_VERSION=2 uv run python evals/gate.py     # try another version before you pin it
    uv run python evals/gate.py --approve            # after reviewing a run: save it as the new baseline

In CI the same file runs inside langfuse/experiment-action, which calls `experiment(context)`.
https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd
"""
import json
import sys
from pathlib import Path

from langchain.tools import tool
from langchain_core.messages import AIMessage, ToolMessage
from langfuse import RegressionError, RunnerContext, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

from research_assistant.agent.agent import build_agent, load_prompt, prompt_label
from research_assistant.agent.tools import calculate, web_search
from research_assistant.core.config import get_settings
from research_assistant.core.langfuse import init_langfuse
from research_assistant.evaluators import CHECKS, case_passed, pass_rate

DATASET = "research-assistant-regression"
BASELINE = Path(__file__).with_name("approved-baseline.json")


def make_task(settings, prompt):
    def task(*, item, **kwargs) -> dict:
        """One case: the agent with the branch's prompt; web_search replays the results recorded for this case."""
        recorded = item.metadata["search_results"]

        @tool("web_search", description=web_search.description)
        def replay_search(query: str) -> list[dict]:
            return recorded  # every query gets the recorded page, as if the web had nothing better

        agent = build_agent(settings, prompt, tools=[replay_search, calculate])
        with propagate_attributes(prompt=prompt, version=prompt_label(prompt)):  # links generations to the prompt
            result = agent.invoke({"messages": [{"role": "user", "content": item.input["question"]}]},
                                  {"recursion_limit": 20, "callbacks": [CallbackHandler()]})
        messages = result["messages"]
        return {"answer": [m for m in messages if isinstance(m, AIMessage)][-1].text,
                "tools": [m.name for m in messages if isinstance(m, ToolMessage)]}
    return task


def verdicts(result, items) -> dict[str, bool]:
    """case id -> passed. A case whose task or evaluators crashed has no case_passed score: it counts as failed."""
    out = {item.id: False for item in items}
    for r in result.item_results:
        scores = {e.name: e.value for e in r.evaluations}
        out[r.item.id] = scores.get("case_passed") == 1
    return out


def experiment(context: RunnerContext):
    settings = get_settings()
    prompt = load_prompt(settings)
    if prompt.is_fallback:
        raise RuntimeError("Langfuse prompt not reachable: the gate must test the real prompt version")
    result = context.run_experiment(
        name="regression-gate", run_name=f"{prompt_label(prompt)} gate", task=make_task(settings, prompt),
        evaluators=[*CHECKS, case_passed], run_evaluators=[pass_rate], max_concurrency=8,
        metadata={"prompt": prompt_label(prompt), "model": settings.model})

    approved = json.loads(BASELINE.read_text())["cases"] if BASELINE.exists() else {}
    current = verdicts(result, context.data)
    newly_failing = sorted(c for c, ok in approved.items() if ok and current.get(c) is False)
    missing = sorted(set(approved) - set(current))  # a case deleted from the dataset must not pass silently
    for case_id, ok in sorted(current.items()):
        was = approved.get(case_id)
        mark = "NEW" if was is None else ("REGRESSION" if was and not ok else ("FIXED" if ok and not was else ""))
        print(f"{'PASS' if ok else 'FAIL'}  {case_id:30} baseline={'-' if was is None else ('PASS' if was else 'FAIL')}"
              f"  {mark}")
    print(f"pass_rate {sum(current.values())}/{len(current)} · newly failing {len(newly_failing)} · "
          f"missing {len(missing)} · {result.experiment_url or ''}")
    if newly_failing or missing:
        raise RegressionError(result=result, metric="newly_failing_cases", value=len(newly_failing) + len(missing),
                              threshold=0, message="cases that passed in the approved baseline now fail: "
                              + ", ".join(newly_failing + [f"{m} (missing)" for m in missing]))
    return result  # experiment-action renders the scores and item results of the returned experiment in the PR


if __name__ == "__main__":  # local run; in CI experiment-action builds the context and calls experiment()
    init_langfuse(get_settings())
    langfuse = get_client()
    items = langfuse.get_dataset(DATASET).items
    try:
        result = experiment(RunnerContext(client=langfuse, data=items))
    except RegressionError as exc:
        print(f"GATE FAILED: {exc}")
        sys.exit(1)
    finally:
        langfuse.flush()
    if "--approve" in sys.argv:  # a person decides when a run becomes the baseline, never the CI job
        baseline = {"dataset": DATASET, "prompt": prompt_label(load_prompt(get_settings())), "cases": verdicts(result, items)}
        BASELINE.write_text(json.dumps(baseline, indent=2) + "\n")
        print(f"saved {BASELINE.name}")
    print("GATE PASSED")
