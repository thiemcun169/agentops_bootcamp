# Lab conventions (AgentOps)

How every session folder of this repository is organised. AgentOps teaches how to run an agent as a software
product, so its labs are **repositories and command-line tools**, not notebooks. (Agent Engineering labs are notebooks;
see `agent_engineering_bootcamp/docs/lab_conventions.md`.)

## Language and tone
- Everything is in **English** (READMEs, code, comments). Short sentences, real commands, links to official docs.

## Chain of sessions
- `sessions/NN_<slug>/` holds the service **at the end of session NN**: copy session NN−1, then add what session NN
  teaches. Never import from another session folder.
- Session 01 also has `starter/` (the messy prototype students standardise). No other session has a starter.
- Keep core pins identical across sessions and bump them together.

## Session folder
```
sessions/NN_<slug>/
  README.md            goal, folder tree, setup, lab steps with a time table, real outputs, troubleshooting, references
  pyproject.toml       [project] with exact pins (==); [dependency-groups] dev = pytest, ipykernel, …;
                       uv_build backend, [project.scripts] entry point
  uv.lock              committed; installs use `uv sync --frozen`
  .python-version      3.12
  .env.example         every key/setting the code reads; real values only in .env (git-ignored)
  .gitignore           the student's repo ignore file (.env first)
  .vscode/             settings.json + extensions.json (OS-neutral)
  src/research_assistant/   the package (same name in every session)
  tests/               pytest, offline by default (no key, no network)
  baselines/           input.json + <release>/run_<time>.json (committed)
  starter/             Session 01 only
```
Environment name: `venvAO<NN>` (`export UV_PROJECT_ENVIRONMENT=venvAO01 && uv sync --frozen`). The session folder is
the project root; nothing is installed at the repository root.

## The agent (same in every session)
- `research_assistant`: LangChain `create_agent` with `web_search` (Tavily, `MAX_SEARCH_RESULTS`, default 3) and
  `calculate` (arithmetic only). Small and cheap: one run is about 8–18k input tokens, about $0.001–0.002.
- Model: `openai:gpt-6-luna`, the same model as Agent Engineering (instructor's choice, 2026-11-02). Its model page
  lists `gpt-6-luna` itself under *Snapshots* (no dated variant), so the ID is the pinned version
  (https://developers.openai.com/api/docs/models/gpt-6-luna). It is a reasoning model: read answers with
  `message.text`, not `.content` (a list of blocks). Check https://developers.openai.com/api/docs/deprecations at the
  start of every cohort and move every session together when a shutdown date appears.
- Prompt in `src/research_assistant/prompts/*.md` until Session 06 moves prompts to Langfuse prompt management.
- Settings: `pydantic-settings`, keys as `SecretStr`, `APP_ENV` = `dev` | `staging` | `prod`.

## README (per session)
1. Goal (2–3 sentences). 2. Folder tree. 3. Setup: env (`uv sync --frozen`), keys (where to get each one, step by
step), IDE. 4. Lab: time table (core ≈ 50 min, extension ≈ 10 min; challenges marked with their minutes), then one
part per row with the **exact commands and their real output** (paths replaced by `~`, keys never printed).
5. Troubleshooting with the real error messages. 6. References. No dates, no instructor names, no instructor notes.

## Students vs. maintainers
- Students build their own repository outside `agentops_bootcamp/` and push it to their own GitHub account; session
  folders are the answer key.
- Maintainers never create a git repository inside a session folder, never commit `.env`, and rehearse every git
  command of a README on a temporary copy outside the repository before pasting its output.

## Code style
- Code close to the official docs (LangChain, uv, pydantic-settings, FastAPI later), no wrappers around the library.
- `logging` with `level` from settings; one INFO line per tool call; silence `httpx`, `httpx2`, `openai` INFO logs;
  `print` only for results.
- Tools return recoverable errors to the model as text. Nothing machine-specific in code or saved outputs.

## Before reporting a session as done
1. Fresh copy (no venv, no `.env`): run every README command exactly as written; `uv run pytest -q`.
2. Run the agent and the baseline for real (twice for the baseline), read the outputs back, check no key is printed
   and no absolute path is saved (`grep -r "/home/\|/mnt/\|/Users/" baselines`).
3. Check the session slides that show lab code, commands or outputs and fix any mismatch.
