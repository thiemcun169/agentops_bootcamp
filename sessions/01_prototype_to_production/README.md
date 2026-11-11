# Session 01 — From Prototype to Production

## Goal

You start from a prototype agent that "works on my machine": a notebook with the key handling, the model, the prompt
and the tools all mixed together, and no pinned versions. You turn it into **your own repository** that anyone can
rebuild: a `src/` package managed by uv with a lockfile, settings per environment with secrets outside the code, the
prompt in a file, a model ID recorded in config, tests, a tagged release `v0.1.0` on GitHub, and a **baseline** run that
records what that release produced. Sessions 02–10 build on this repository.

The agent is small on purpose: one LangChain `create_agent` with two tools, `web_search` (Tavily) and `calculate`.

## What is in this folder

```
01_prototype_to_production/
  starter/
    prototype.ipynb          the messy prototype (run it, find the problems)
    requirements.txt         unpinned dependencies, shown as a problem (do not install from it)
  src/research_assistant/    the solution: the prototype as a package
    __main__.py              command line, with the if __name__ == "__main__" guard
    config.py                Settings from environment variables and .env (pydantic-settings)
    tools.py                 web_search, calculate
    agent.py                 build_agent(), ask(): answer + model ID + tokens + cost
    baseline.py              baseline smoke run -> baselines/<release>/run_<time>.json
    prompts/system_prompt.md the system prompt, versioned with the code
  tests/                     offline tests (no key, no network)
  baselines/                 input.json (fixed question) + v0.1.0/ (two real runs)
  pyproject.toml  uv.lock  .python-version  .env.example  .gitignore
```

The folder is the **answer key**. You build your own repository **outside** `agentops_bootcamp/` (step 2), so it is
not nested inside this repository.

## Setup (in this folder)

1. **Create the environment** (Python 3.12 and the exact versions from `uv.lock`):
   ```bash
   # macOS / Linux
   export UV_PROJECT_ENVIRONMENT=venvAO01 && uv sync --frozen
   ```
   ```powershell
   # Windows PowerShell
   $env:UV_PROJECT_ENVIRONMENT="venvAO01"; uv sync --frozen
   ```
   Keep this terminal: every later `uv run` uses `venvAO01`.
2. **Register the notebook kernel**: `uv run python -m ipykernel install --user --name venvAO01 --display-name venvAO01`
3. **Keys**: copy `.env.example` to `.env` (same folder) and fill in:
   - `OPENAI_API_KEY`: https://platform.openai.com/api-keys → *Create new secret key* → copy it once (it is shown only
     once). The account needs a little credit; one run of the agent costs well under $0.01.
   - `TAVILY_API_KEY`: https://app.tavily.com → sign in → *API Keys* → copy the default key (the free plan has 1,000
     API credits per month; one run of the agent uses a few searches).
4. **IDE**: open **this folder** in VS Code or Cursor (*File → Open Folder*), open `starter/prototype.ipynb`, then
   *Select Kernel → Jupyter Kernel… → venvAO01*.

Check: `uv run research-assistant --show-config` prints your settings with both keys shown as `**********`.

## Lab (≈ 60 min: core 50 min + extension 10 min)

| Time | Part | Who |
|---|---|---|
| 0–8 | 1. Run the prototype and list what breaks | you |
| 8–20 | 2. **Challenge A** (8 min): package the prototype with uv; then the solution is live-coded (4 min) | you → instructor |
| 20–30 | 3. **Challenge B** (7 min): settings, secrets, prompt file, model in config; then live-coded (3 min) | you → instructor |
| 30–35 | 4. Tests | you |
| 35–45 | 5. Git and GitHub: commit, branch, pull request, tag `v0.1.0` | you |
| 45–50 | 6. Baseline: run it twice, compare, discuss | you + class |
| 50–60 | Extension: rebuild from the tag in a fresh clone, GitHub Release, protected `main` | optional |

### 1. Run the prototype and list what breaks (8 min)

Open `starter/prototype.ipynb` and run the cells **out of order**: the four cells from the top, then the *Scratch*
cell (`SYSTEM_PROMPT = "... Reply in one sentence."`), then the question cell again. The saved notebook shows exactly
that run: the question cell has execution count **[6]**, the scratch cell below it **[5]**, and the answer is one
sentence although the prompt you can read above asks for 3 bullet points:

```
Cold-climate air-source heat pumps typically achieve a seasonal COP of about 2–3; at a representative COP of 2.5,
delivering 12,000 kWh of heat requires about **4,800 kWh of electricity** (12,000 ÷ 2.5).

served model: gpt-6-luna | 7.4s
```

Write down every problem you see. The list to compare with:

| In the prototype | What goes wrong |
|---|---|
| hidden state (cells run in any order) | the answer depends on the run history, not on the code you read |
| `# OPENAI_API_KEY = "<paste-your-key-here>"` | a pasted key goes into git history and every copy of the notebook |
| `MODEL = "gpt-6-luna"` in a cell | the model is not in config and no run records which model answered |
| prompt inside a cell | a prompt change is invisible in review (see the `.ipynb` diff on the slides) |
| `requirements.txt` without versions | `pip install -r` installs whatever is newest on the day you install |
| `eval(expression)` in `calculate` | runs any Python the model sends |
| no tests, no record of past answers | nobody can tell whether yesterday's answer can be reproduced |

### 2. Challenge A — package the prototype with uv (8 min + 4 min live-code)

Work **outside** `agentops_bootcamp/`, for example in your home folder. `--vcs none` stops uv from creating a git
repository before `.gitignore` is ready (step 3); `--python 3.12` avoids picking an older Python installed on your
machine.

```bash
cd ~
uv init --package --vcs none --python 3.12 research-assistant
cd research-assistant
export UV_PROJECT_ENVIRONMENT=venvAO01        # PowerShell: $env:UV_PROJECT_ENVIRONMENT="venvAO01"
uv add langchain==1.4.2 langchain-openai==1.6.6 tavily-python==0.8.4 pydantic-settings==2.16.2
uv add --dev pytest==9.1.1
uv run research-assistant
```
Real output:
```
Initialized project `research-assistant` at `~/research-assistant`
Using CPython 3.12.3 interpreter at: /usr/bin/python3.12
Creating virtual environment at: venvAO01
Resolved 49 packages in 6ms
Installed 48 packages in 13ms
...
Hello from research-assistant!
```
You declared 4 packages; `uv.lock` pins all of them with every sub-dependency (54 packages with pytest), each with its
exact version and file hashes. `pyproject.toml` says what the app needs; `uv.lock` says exactly what was installed.

**Challenge:** move the notebook code into `src/research_assistant/`: `tools.py` (the two tools), `agent.py` (build the
agent, ask one question) and `__main__.py` (a `main()` that reads the question from the command line, and the
`if __name__ == "__main__":` guard). Point the script entry in `pyproject.toml` to it:
```toml
[project.scripts]
research-assistant = "research_assistant.__main__:main"
```
Then `uv run research-assistant "What is a heat pump COP?"` must answer. Compare with this folder's
`src/research_assistant/` (copy what you are missing).

### 3. Challenge B — settings, secrets, prompt, model (7 min + 3 min live-code)

1. `config.py`: a `Settings(BaseSettings)` class with `app_env` (`dev` / `staging` / `prod`), the two keys as
   `SecretStr`, `model`, `max_search_results`. Values come from environment variables first, then `.env`.
2. Copy this folder's `.env.example` and `.gitignore` into your project; `cp .env.example .env` and fill in the keys.
   **Check that `.gitignore` lists `.env` before you ever run `git init`.**
3. Move the system prompt to `src/research_assistant/prompts/system_prompt.md` and load it from `config.py`.
4. Put the model in config: `MODEL=openai:gpt-6-luna`. Use an ID listed under *Snapshots* on the provider's model page
   (for `gpt-6-luna` the ID itself is the snapshot; for `gpt-5.4-mini` the alias points to `gpt-5.4-mini-2026-03-17`).

```bash
uv run research-assistant --show-config
APP_ENV=staging uv run research-assistant --show-config     # PowerShell: $env:APP_ENV="staging"; uv run ...
APP_ENV=production uv run research-assistant --show-config  # rejected: not dev/staging/prod
```
Real output (first and third command):
```
{
  "app_env": "dev",
  "openai_api_key": "**********",
  "tavily_api_key": "**********",
  "model": "openai:gpt-6-luna",
  "max_search_results": 3,
  ...
}
Invalid settings: APP_ENV. Set them in .env (see .env.example) or as environment variables.
```
Without a `.env` the app stops before calling any API:
`Invalid settings: OPENAI_API_KEY, TAVILY_API_KEY. Set them in .env (see .env.example) or as environment variables.`
Run the agent once:
```bash
uv run research-assistant "What seasonal COP do air-source heat pumps typically reach in cold climates, and how many kWh of electricity does one need to deliver 12,000 kWh of heat at that COP?"
```
Real output (one run; yours will differ):
```
INFO | research_assistant.tools | web_search('cold climate air source heat pump seasonal coefficient of performance average seasonal COP') -> 3 results
INFO | research_assistant.tools | web_search('cold climate heat pump field study seasonal COP 2.5 heating season coefficient performance') -> 3 results
... (4 more web_search lines)
INFO | research_assistant.tools | calculate(12000/2.5) -> 4800.0
- A reasonable typical seasonal COP for an air-source heat pump in a cold climate is **about 2.5**. Field results vary: ...
- At COP 2.5, delivering **12,000 kWh of heat** takes **4,800 kWh of electricity** (12,000 ÷ 2.5).
...
[dev] model=gpt-6-luna {'latency_s': 30.5, 'model_calls': 4, 'tool_calls': ['web_search', 'web_search', 'web_search', 'web_search', 'web_search', 'web_search', 'calculate'], 'input_tokens': 8259, 'output_tokens': 925, 'cost_usd': 0.00129}
```

### 4. Tests (5 min)

Copy `tests/` from this folder. The tests need no key and no network: settings read from the environment, a missing
key stops the app at start-up, an unknown `APP_ENV` is rejected, the model is a pinned snapshot ID (not an alias), the prompt file is in
the package, `calculate` refuses code.
```bash
uv run pytest -q
```
```
.......                                                                  [100%]
7 passed in 0.67s
```

### 5. Git and GitHub (10 min)

```bash
git init -b main
git status --short              # .env and venvAO01/ must NOT be listed
git check-ignore -v .env        # .gitignore:2:.env   .env
git add . && git commit -m "Package the prototype: src/ layout, settings, prompt file"
```
On https://github.com/new create an **empty** repository `research-assistant` (no README, no .gitignore), then:
```bash
git remote add origin https://github.com/<you>/research-assistant.git
git push -u origin main
```
Work on a branch and merge it through a pull request:
```bash
git switch -c add-tests
git add tests && git commit -m "Add offline tests for settings and tools"
git push -u origin add-tests
```
On GitHub: *Compare & pull request* → *Create pull request* → *Merge pull request*. Then update `main` and tag the
release:
```bash
git switch main && git pull
git tag -a v0.1.0 -m "First reproducible release"
git push origin v0.1.0
git log --graph --oneline --decorate
```
Real output (a local rehearsal of the same steps, where `git merge --no-ff add-tests` stood in for the GitHub merge
button, which also creates a merge commit):
```
*   ce82f53 (HEAD -> main, tag: v0.1.0) Merge pull request #1 from add-tests
|\
| * eeb504b (add-tests) Add offline tests for settings and tools
|/
* 2fce2cf Package the prototype: src/ layout, settings, prompt file
```
If you committed tests in step 4 already, make any small change on the branch instead (for example a line in your
README).

### 6. Baseline (5 min)

Copy `baselines/input.json` and `src/research_assistant/baseline.py` if you do not have them yet. At the tag, run the
fixed question twice:
```bash
uv run research-assistant --baseline
uv run research-assistant --baseline
```
```
saved baselines/v0.1.0/run_2026-11-02T033543Z.json
saved baselines/v0.1.0/run_2026-11-02T033607Z.json
```
Each file holds the **manifest** (what produced the run), the input, the output and the metrics. The two real runs in
`baselines/v0.1.0/`:

| | run 1 | run 2 |
|---|---|---|
| manifest: git, uv.lock, prompt, model, config | `v0.1.0` · `ce82f53` · lock `db76cdbb27fc` · prompt `439f527b5660` · `gpt-6-luna` · dev, 3 results | identical |
| served model | `gpt-6-luna` | `gpt-6-luna` |
| model calls · tool calls | 6 · web_search ×3, calculate ×2 | 5 · web_search ×7, calculate ×2 |
| latency | 22.2 s | 23.4 s |
| tokens in / out | 7,751 / 408 | 12,418 / 733 |
| cost | $0.00098 | $0.00161 |
| answer | "...about **2.5–3.0** ... about **4,000–4,800 kWh**" | "...about **2.5–2.8** ... roughly **4,300–4,800 kWh**" |

Commit the baseline: `git add baselines && git commit -m "Record v0.1.0 baseline" && git push`.

What one run looks like inside (three more real runs of the same code, model and question, `gpt-6-luna`, one line per model call:
input/output tokens, then what the model asked for):

| Trace run | Steps | Input tokens | Latency | Cost |
|---|---|---|---|---|
| 1 | model (185/65) → search → model (754/57) → search → model (1,320/54) → search → model (1,912/97) → search → model (2,450/254) → calculate ×2 + search → model (3,239/80) → calculate → model (3,336/260) → answer | 13,196 | 33.4 s | $0.0018 |
| 2 | model (185/31) → search → model (763/35) → search → model (1,281/273) → calculate ×2 + search ×2 → model (2,778/176) → calculate → model (2,971/187) → answer | 7,978 | 21.8 s | $0.0012 |
| 3 | model (185/39) → search → model (831/135) → search ×3 → model (2,340/147) → search → model (3,111/39) → search → model (3,748/102) → calculate ×2 → model (3,876/105) → calculate → model (3,998/147) → answer | 18,089 | 28.6 s | $0.0022 |

The input grows at every call because each tool result is sent back to the model with the whole conversation.

**Discussion:** the manifests are identical, so this is the same version. Why are the answers, the latency and the
tokens different? What should a baseline therefore store, and how would you decide that a new version is "as good as"
`v0.1.0`? (Across these runs the same question used 7,751 to 18,089 input tokens: what does that say about the cost
of one run?)

### Extension (10 min, optional)

- **Rebuild from the tag**, as a teammate would:
  ```bash
  git clone https://github.com/<you>/research-assistant.git teammate && cd teammate
  git checkout v0.1.0
  export UV_PROJECT_ENVIRONMENT=venvAO01 && uv sync --frozen && uv run pytest -q
  ```
  Real output: `Installed 78 packages`, `7 passed`. Then add a package to `pyproject.toml` by hand (without `uv lock`)
  and compare:
  ```
  $ uv sync --locked
  Resolved 86 packages in 8ms
  error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.

  hint: To update the lockfile, run `uv lock`.
  $ uv sync --frozen
  Installed 1 package in 0.96ms
  ```
  `--locked` refuses a stale lockfile; `--frozen` installs the old lock without checking. For a production install
  without the dev group: `uv sync --frozen --no-dev`.
- **GitHub Release**: *Releases → Draft a new release → choose tag v0.1.0 → Generate release notes → Publish*.
- **Protect `main`**: *Settings → Branches → Add branch ruleset* (or *Add classic branch protection rule*) → require a
  pull request before merging. Then try `git push origin main` directly from a new commit.
- Add a new setting (for example `MAX_STEPS`) to `Settings` and `.env.example`, and a test for it.

## Troubleshooting

- `uv add` fails with *"pydantic-settings==2.16.2 depends on Python>=3.11"*: the project picked an older Python on your
  machine. Re-create it with `--python 3.12` (or put `3.12` in `.python-version`) and run `uv sync`.
- `Invalid settings: OPENAI_API_KEY, TAVILY_API_KEY`: `.env` is missing or not in the folder you run from; run the
  command from the project root.
- `git status` lists `.env`: add `.env` to `.gitignore` **before** `git add`. If a key was ever committed, revoke it on
  the provider's site; deleting the file does not remove it from history.
- `fatal: not a git repository` in the baseline manifest (`git_describe: null`): run `git init` first (step 5).
- The notebook kernel `venvAO01` is not listed: run setup step 2, then *Developer: Reload Window*.
- GitHub push asks for a password: use a personal access token or `gh auth login`
  (https://docs.github.com/en/get-started/getting-started-with-git/caching-your-github-credentials-in-git).

## References

- uv projects: https://docs.astral.sh/uv/concepts/projects/init/ · locking and syncing:
  https://docs.astral.sh/uv/concepts/projects/sync/
- pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- The Twelve-Factor App, Config: https://12factor.net/config
- GitHub flow: https://docs.github.com/en/get-started/using-github/github-flow · releases:
  https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Semantic Versioning: https://semver.org/
- OpenAI model `gpt-6-luna` (snapshots, prices): https://developers.openai.com/api/docs/models/gpt-6-luna ·
  deprecations: https://developers.openai.com/api/docs/deprecations
- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
