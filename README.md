# AgentOps — Labs

**Deploy, Operate and Continuously Improve AI Agents** · COLE

Hands-on labs of the AgentOps course: take one small AI agent from a prototype on a laptop to a service that runs in
the cloud with CI/CD, observability, continuous evaluation, cost and latency control, durable execution and a
production runbook. 10 sessions × 2 hours.

## Syllabus

| #  | Session | Topics |
| -- | ------- | ------ |
| 01 | AgentOps: From Prototype to Production | lifecycle of an agent product; MLOps, LLMOps and AgentOps; project structure, dependencies, environment config; Git/GitHub workflow and releases; versioning code and agent components; reproducible baseline |
| 02 | Serving an Agent with FastAPI | agent harness recap; Agent API with FastAPI; SSE streaming of progress and tool activity; user/session metadata, isolation, errors, health checks, application logs |
| 03 | Containerizing Agents with Docker | image, container, registry; Dockerfile, build cache, pinning; env vars, secrets, networking, volumes; health check, graceful shutdown; Docker Compose |
| 04 | Deploying an Agent to Cloud | cloud architecture for an Agent API; runtime config, secrets, identity, access control; scaling, logs, versions, rollback, cost; Google Cloud Run |
| 05 | CI/CD with GitHub Actions | CI, CD and release workflow; automated tests for code, API and agent behaviour; environments, deployment versions, rollback |
| 06 | Observability for Agent Systems | logs, metrics, traces, health; prompt management and versioning; structured logs correlated with Langfuse traces; OpenTelemetry, Grafana; debugging a failed request |
| 07 | Continuous Evaluation with Langfuse | AI Engineering Loop; offline and online evaluation; regression datasets; code evaluators, LLM-as-a-judge, human review; quality gate against a baseline |
| 08 | Optimizing Cost and Latency | measuring cost, tokens, latency per model/feature/user/release; bottlenecks; model choice, context, caching, tools, parallelism; AI Gateway |
| 09 | Durable Execution and High Throughput | background runs; API + queue + worker + state/checkpoint; task lifecycle, retry, cancel, resume, idempotency; RabbitMQ + Celery |
| 10 | Production Game Day and Final Project | readiness checklist; release approval, rollback, verification; incident response; ownership and runbook |

## How the repository works

Each `sessions/NN_<slug>/` folder holds the agent service **as it stands at the end of session NN**, copied from
session NN−1 plus what that session adds. Every session is independent: its own README, `pyproject.toml` + `uv.lock`,
`.env.example` and environment (`venvAO01`, `venvAO02`, …). You can start at any session.
Session 01 also has `starter/`, the messy prototype you standardise.

You build **your own repository** (on your GitHub account) during Session 01 and keep extending it; the session
folders here are the reference solution for each step.

## Session 0 setup (before the first class, ~30 min)

1. **Git**: `git --version`. If missing: https://git-scm.com/downloads (Windows: default options; macOS:
   `xcode-select --install`). Then set your name and email once:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
2. **uv** (installs Python 3.12 for each lab; no separate Python needed):
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

   Reopen the terminal, check `uv --version`, then `uv python install 3.12`.
3. **VS Code** (https://code.visualstudio.com/) or **Cursor** (https://cursor.com/) with the **Python**
   (`ms-python.python`) and **Jupyter** (`ms-toolsai.jupyter`) extensions.
4. **GitHub account**: https://github.com/signup. To push from the terminal, sign in once with the GitHub CLI
   (`gh auth login`, https://cli.github.com/) or create a personal access token
   (https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
5. **Provider keys** (kept only in each session's `.env`, never in code or git):
   - OpenAI: https://platform.openai.com/api-keys → *Create new secret key*; add a few dollars of credit in *Billing*.
   - Tavily (web search): https://app.tavily.com → *API Keys* (free plan is enough).
6. **Clone this repository**:
   ```bash
   git clone <this-repo-url> agentops_bootcamp
   cd agentops_bootcamp/sessions/01_prototype_to_production
   ```
   Then follow that session's **Setup**.

Later sessions add Docker Desktop (Session 03), a Google Cloud account with billing (Session 04) and a Langfuse
account (Session 06); each session README says what to install.

## Rules for every lab

- Run the setup commands **inside the session folder**; `export UV_PROJECT_ENVIRONMENT=venvAONN` first, then use `uv`
  for every command (`uv sync --frozen`, `uv run …`).
- Open **the session folder** in the IDE (File → Open Folder), not the whole repository.
- Never commit `.env` or keys. Do not `pip install` into a lab environment; add packages with `uv add`.

Contributors: see [docs/lab_conventions.md](docs/lab_conventions.md).
