# Session 07 — Continuous Evaluation with Langfuse

## Goal

The agent API runs and every run is a Langfuse trace. Today its quality is measured all the time, and a bad change
is stopped before it reaches users:
- **online**: user feedback and evaluators score production traces as they arrive;
- **from production to tests**: a failing production trace becomes a case of a regression dataset;
- **offline**: an experiment runs the dataset on a candidate prompt and compares every case with an approved baseline;
- **in the release workflow**: a GitHub Actions check runs that experiment on each pull request and blocks the merge
  when a case that passed now fails.

```
users ──► agent API ──► Langfuse trace (environment production)
            │ 👍/👎 ──► score user-feedback         │ online evaluators: cites_sources (100%), answers_question (50%)
            │                                       ▼
            │                     failing trace ──► dataset research-assistant-regression (+ source_trace_id)
            ▼                                                     │
pull request: prompt.toml version 1 → 2 ──► eval-gate (GitHub Actions) ──► experiment on the dataset
                                                 │ compare each case with evals/approved-baseline.json
                                                 └► red: merge blocked · green: merge, deploy, new traces
```

The service is the one of Session 04 (FastAPI, SSE, Postgres checkpointer, Cloud Run). Sessions 05 and 06 set up
CI/CD and Langfuse tracing; this folder contains the minimum of both that evaluation needs, so it also works on its
own: one trace per run, the prompt from Langfuse Prompt Management, and one workflow.

## What is in this folder

```
07_continuous_eval/
  src/research_assistant/
    core/langfuse.py          new: the Langfuse client (environment, release)
    agent/prompt.toml         new: the prompt version this release uses (bumped in a pull request)
    agent/agent.py            prompt from Langfuse (fallback file only if Langfuse is unreachable)
    api/routers/runs.py       root observation agent-run per run; trace_id in the metadata event;
                              POST …/runs/{run_id}/feedback → score user-feedback
    evaluators.py             new: code checks shared by the gate and the production scorer
  static/                     the UI, with 👍 / 👎 under each answer
  prompts/                    texts to paste into Langfuse: prompt v2, v3 and the judge
  evals/
    cases.jsonl               16 designed cases (criteria, not reference answers)
    upload_dataset.py         creates the dataset research-assistant-regression
    add_from_trace.py         a production trace → a dataset item
    gate.py                   the experiment + per-case comparison (local and in CI)
    approved-baseline.json    verdict per case of the reviewed run
    score_production.py       extension: score yesterday's production runs on a schedule
    online/cites_sources.py   the code evaluator pasted into Langfuse
  .github/workflows/eval-gate.yml   the gate on every pull request
  examples/send_traffic.py    8 questions as alice and bob (examples/traffic.txt)
  compose.yaml  Dockerfile  deploy/  tests/  pyproject.toml (0.7.0)  uv.lock
```

The folder is the **answer key**. Work in **your own repository** (this folder is its root, so the workflow is at
`.github/workflows/eval-gate.yml`).

## Setup

1. **Environment**
   ```bash
   export UV_PROJECT_ENVIRONMENT=venvAO07 && uv sync --frozen
   uv run pytest -q          # 26 passed (no key, no network: Langfuse is off in the tests)
   ```
2. **Langfuse project.** Sign up at https://cloud.langfuse.com (EU) or https://us.cloud.langfuse.com (US), create an
   organisation and a project, then *Settings → API Keys → Create new API keys*.
3. **Keys.** Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`, `TAVILY_API_KEY`, `LANGFUSE_PUBLIC_KEY`,
   `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` (the region of your project).
4. **Prompt v1.** Langfuse → *Prompts → New prompt*: name `research-assistant`, type *Text*, paste
   `src/research_assistant/agent/prompts/system_prompt.md`, label `production`, *Save*. It becomes version 1, the
   version `agent/prompt.toml` pins.
5. **LLM connection** (for the judge): *Settings → LLM Connections → Add new LLM API key*: provider OpenAI, your key.
6. **GitHub** (Part 5): your repository on GitHub with this folder as its root.

## Lab (≈ 60 min core + 15 min extension)

| Part | Minutes | What you do | Output |
|---|---|---|---|
| 1 | 8 | Run the service as production, send traffic, give feedback | traces + score `user-feedback` |
| 2 | 12 | Online evaluators: code check on every run, judge on half | scores `cites_sources`, `answers_question` |
| 3 | 10 | Regression dataset: 16 designed cases + 1 production failure | dataset with 17 items |
| 4 | 12 | Experiment: approve v1 as baseline, compare candidate v2 | two experiment runs, compared per case |
| 5 | 18 | Eval gate in GitHub Actions: red PR, green PR | required check on `main` |
| 6 (ext.) | 15 | Score production on a schedule; alert on a score | `score_production.py`, an alert |

### 1. Traffic and user feedback (8 min)

Run the service as production would (Docker Compose or Cloud Run work the same way; set the variable there):
```bash
LANGFUSE_TRACING_ENVIRONMENT=production uv run fastapi run
```
```
INFO research_assistant.api … | agent ready in 952 ms: model=openai:gpt-6-luna prompt=research-assistant v1 checkpointer=memory langfuse_env=production
```
Every run now sends its `trace_id` in the first event; the trace id is derived from the session and run ids, so the
feedback route finds the trace without storing anything:
```
event: metadata
data: {"run_id": "4e3ee8df", "session_id": "7daffac2-1ef8-4de3-93ee-22c886eed230", "trace_id": "609abf77ecd19afb67c210b955330a06"}
```
Feedback on that run (the UI's 👍 / 👎 send the same request):
```bash
curl -s -X POST $API/v1/sessions/$SID/runs/$RUN/feedback -H "$ALICE" -H "Content-Type: application/json" \
     -d '{"value": true}'
{"trace_id":"609abf77ecd19afb67c210b955330a06","name":"user-feedback","value":true}            # HTTP 202
# the same request with Bob's token: 404 Session … not found (he does not own the session)
```
Send the 8 questions of `examples/traffic.txt` (in another terminal):
```bash
uv run python examples/send_traffic.py
```
```
trace 9f6a97c0 run 8f46cafb 8.7 s tools=['web_search'] | How long does a heat pump last before it needs replacing?
trace fca6e97d run 694cec65 30.6 s tools=['web_search', 'web_search', 'web_search', 'calculate', … 13 calls] | Compare the yearly running cost …
trace 34741301 run 008c8074 - s tools=Internal Server Error | List the five largest EV battery makers and their market sha
trace 92dd19d0 run cf00650f 6.5 s tools=['web_search', 'calculate'] | A heat pump costs 14,000 EUR and saves 1,300 EUR …
…
```
Open `http://localhost:8000/ui/`, ask a question, click 👎 and write why. In Langfuse → *Tracing*, filter
`Environment = production`: one trace per run, root observation `agent-run` with the question as input and
`{"answer", "tools"}` as output, the score `user-feedback` on the trace, and each generation linked to
`research-assistant` version 1.

Look at the failed run: `GraphRecursionError … Recursion limit of 20 reached` in the server log, level ERROR on the
trace. The agent searched again and again for market shares it did not find. Keep its trace id for Part 3.

### 2. Online evaluators (12 min)

Langfuse → *Evaluators → New evaluator*:

1. **Code evaluator** (Python) `cites_sources`: paste `evals/online/cites_sources.py`. Test it on a production
   `agent-run` observation (*Run test on this sample*). It runs inside Langfuse: standard library only, no network,
   at most 2 seconds.
2. **LLM-as-a-Judge** `answers_question`: paste `prompts/judge_answers_question.txt`; output *Boolean*; in
   *Map variables to data* map `question` to the observation input (JSON path `$.question`) and `answer` to the
   output (`$.answer`); model `gpt-6-luna` from your LLM connection.
3. **Rules** (which observations get scored): filter `Is Root Observation = true`, `Environment any of production`,
   `Trace Name any of agent-run`; sampling **100 %** for `cites_sources` (free), **50 %** for the judge (each call
   costs tokens: read the cost estimate before you enable it).

Send traffic again (`uv run python examples/send_traffic.py`). New production observations get scores with source
`EVAL`; traffic of the gate (environment `sdk-experiment`) and of your laptop (`development`) is not scored.

### 3. Regression dataset (10 min)

Create the dataset from the designed cases. Each case stores the search results of its question, so the gate can
replay them instead of calling Tavily:
```bash
uv run python evals/upload_dataset.py
```
```
+ num-heat-pump-cop
+ num-ev-battery-degradation
…
+ def-lfp
dataset research-assistant-regression: 16 items
```
`expected_output` holds criteria (`must_search`, `must_cite`, `must_calculate`), not a reference answer: two good
answers never match word for word.

Turn the production failure of Part 1 into a case (the item keeps a link to the trace):
```bash
uv run python evals/add_from_trace.py <trace_id of the failed run> --must-search --must-cite
```
```
+ prod-51c7bf0c: 'List the five largest EV battery makers and their market share.' expected={'must_search': True, 'must_cite': True} search_results=26
```
(The UI way: on the observation, *+ Add to dataset*.)

### 4. Experiment: baseline and candidate (12 min)

Run the dataset on the pinned prompt (v1) and, after reading the result, save it as the approved baseline:
```bash
uv run python evals/gate.py --approve
```
```
PASS  calc-battery-hours             baseline=-  NEW
…
FAIL  mixed-heat-pump-savings        baseline=-  NEW
…
FAIL  prod-51c7bf0c                  baseline=-  NEW
pass_rate 15/17 · newly failing 0 · missing 0 · https://…/experiments/results?…
saved approved-baseline.json
GATE PASSED
```
Two cases fail with v1: the agent hits the recursion limit when the results do not answer the question. They are in
the baseline as known failures; they do not block, but a case that passed must keep passing.

Create the candidate: Langfuse → *Prompts → research-assistant → New version*, paste
`prompts/research-assistant_v2_short.txt` (shorter answers for a mobile app), no label. Try it without changing the
pin:
```bash
PROMPT_VERSION=2 uv run python evals/gate.py
```
```
FAIL  num-heat-pump-cop              baseline=PASS  REGRESSION
…
pass_rate 6/17 · newly failing 9 · missing 0 · …
GATE FAILED: cases that passed in the approved baseline now fail: mixed-ev-range-winter, …
```
In Langfuse → *Datasets → research-assistant-regression → Experiments*, select the two runs and compare them item by
item: v2 drops the `Sources:` line, so `cites_sources` fails on every factual case.

### 5. The eval gate in GitHub Actions (18 min)

1. Repository → *Settings → Secrets and variables → Actions*: secrets `OPENAI_API_KEY`, `TAVILY_API_KEY`,
   `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`; variable `LANGFUSE_BASE_URL`.
2. Commit `evals/approved-baseline.json`, the workflow and the code to `main`.
3. *Settings → Branches → Add rule* for `main`: *Require status checks to pass*, check `regression`. (Branch
   protection on a private repository needs GitHub Pro; on a public one it is free.)
4. Create prompt version 3 in Langfuse from `prompts/research-assistant_v3_search_budget.txt` (at most 3 searches).
5. Open a pull request that sets `version = 2` in `src/research_assistant/agent/prompt.toml`. The check `regression`
   runs `langfuse/experiment-action`, which calls `experiment()` in `evals/gate.py`, fails, and comments on the PR:
   ```
   ❌ research-assistant v2 gate
   RegressionError: cases that passed in the approved baseline now fail: mixed-ev-range-winter, num-ev-battery-degradation, …
   | pass_rate | 0.353 |
   Item results (17)
   ```
6. Open another pull request with `version = 3`: the check passes and two cases turn from FAIL to PASS:
   ```
   PASS  mixed-heat-pump-savings        baseline=FAIL  FIXED
   PASS  prod-51c7bf0c                  baseline=FAIL  FIXED
   pass_rate 17/17 · newly failing 0 · missing 0 · …
   GATE PASSED
   ```
   The PR comment shows `✅ research-assistant v3 gate`, `pass_rate 1.000` and the 17 item results.
7. Merge it, run `uv run python evals/gate.py --approve` on `main` and commit the new baseline. The CI job never
   writes the baseline: a person approves it.

The gate costs one agent run per case with the OpenAI key (≈ 2–4 minutes for 17 cases) and no Tavily call.

### 6. Extension (15 min)

- **Scheduled scoring.** Score yesterday's production runs with the same checks as the gate (any Python package
  allowed, unlike Langfuse code evaluators):
  ```bash
  uv run python evals/score_production.py --hours 24
  ```
  ```
  Items fetched: 8
  Items processed: 8
  Scores created: 24
  ```
  Run it from cron, Cloud Scheduler or a scheduled workflow (`on: schedule`).
- **Alert.** Langfuse → *Alerts*: average of `cites_sources` over the last hour below 0.9 → webhook or Slack.
  Alerts are evaluated on the aggregate over a time window, not on each score.

## Troubleshooting

- `prompt research-assistant: Langfuse unreachable or no keys, using the fallback file` and `/v1/info` shows
  `(fallback)`: wrong keys or `LANGFUSE_BASE_URL` of the other region. The gate refuses to run on the fallback.
- `Prompt not found` for version 2 or 3: create the version in Langfuse first; the pin only names it.
- No scores from an online evaluator: the rule filters on `Environment = production` and the service runs with
  another `LANGFUSE_TRACING_ENVIRONMENT`; or the judge has no LLM connection (evaluator paused).
- The judge scores everything false: `Map variables to data` points at the whole output instead of `$.answer`.
- Feedback `404`: the session belongs to another user. `422`: `run_id` is not the 8-character id of the
  `metadata` event.
- `Item N failed: Recursion limit of 20 reached`: the agent kept searching; the case counts as failed.
- GitHub `Unable to resolve action astral-sh/setup-uv@v10`: the action publishes release tags only; keep the full
  version.
- GitHub `The job was not started because recent account payments have failed`: Actions minutes of a private
  repository; make the repository public or fix billing.
- `RegressionError` on cases you did not touch: the model answers differently from run to run. Read the two traces
  in Langfuse; if the old answer passed by luck, approve a new baseline after review.

## References

- Langfuse: AI Engineering Loop https://langfuse.com/academy/ai-engineering-loop · online evaluation
  https://langfuse.com/docs/evaluation/get-started/online · LLM-as-a-judge
  https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge · code evaluators
  https://langfuse.com/docs/evaluation/evaluation-methods/code-evaluators · user feedback
  https://langfuse.com/docs/observability/features/user-feedback
- Datasets https://langfuse.com/docs/evaluation/experiments/datasets · experiments via SDK
  https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk · experiments in CI/CD
  https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd · experiment-action
  https://github.com/langfuse/experiment-action
- Prompt management https://langfuse.com/docs/prompt-management/overview · environments
  https://langfuse.com/docs/observability/features/environments
- GitHub protected branches https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
