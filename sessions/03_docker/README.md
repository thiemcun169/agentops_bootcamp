# Session 03 — Containerizing the Agent with Docker

## Goal

In Session 02 the research agent became an HTTP service (`uv run fastapi dev`). Today the **same service** ships as a
**Docker image** that runs the same way on any machine: a multi-stage `Dockerfile` built with `uv`, a `.dockerignore`
that keeps keys and virtual environments out of the image, keys passed **at run time**, a `HEALTHCHECK`, an exec-form
`CMD` so `docker stop` shuts the service down cleanly, and a `compose.yaml` that runs the agent together with
**Postgres**, so sessions and conversations survive a restart. Session 04 deploys exactly this image to Cloud Run.

The agent and the API do not change (same model, prompt, tools and endpoints as Session 02). New in the code: a
checkpointer setting (`CHECKPOINTER=memory|postgres`), a Postgres session store and a `database` check in `/ready`.

## What is in this folder

```
03_docker/
  Dockerfile             new: multi-stage (build: uv + dependencies, runtime: app + .venv, user app, HEALTHCHECK)
  Dockerfile.naive       new: the first Dockerfile of Part 1 (works, but large and slow to rebuild)
  .dockerignore          new: keeps .env, venvAO*, .git, tests … out of the build context
  compose.yaml           new: agent-api + postgres:18, healthchecks, named volume, develop.watch
  .env.db.example        new: Postgres user, password, database (copied to .env.db)
  breaks/                new: the files of the break steps (fake-key Dockerfile, context Dockerfile, two compose overrides)
  scripts/               new: measure_rebuild.sh, measure_stop.sh (the tables of Parts 2 and 4)
  src/research_assistant/
    core/config.py       + CHECKPOINTER, DB_HOST, DB_PORT, POSTGRES_* and db_url
    services/sessions.py MemorySessionStore (Session 02) + PostgresSessionStore (table sessions)
    api/main.py          lifespan: memory or Postgres checkpointer (AsyncPostgresSaver + connection pool)
    api/routers/health.py /ready also checks the database
    agent/  schemas/  api/deps.py  api/errors.py …   unchanged from Session 02 (await on the session store)
  static/  tests/  payloads/  examples/  data/users.json  baselines/  pyproject.toml  uv.lock  .env.example
```

The folder is the **answer key**. Keep working in **your own repository** from Session 02, on a branch `docker`, and
compare with this folder after each challenge.

## Setup (in this folder)

1. **Docker**: Docker Desktop (macOS, Windows) or Docker Engine with the Compose plugin (Linux). Check:
   ```bash
   docker version --format '{{.Server.Version}}'   # this README was produced with 29.2.1
   docker compose version                          # Docker Compose version v5.1.0
   ```
   Pull the base images before class (the first pull takes minutes):
   `docker pull python:3.12 && docker pull python:3.12-slim && docker pull postgres:18`.
2. **Create the environment** (for the tests and `uv run` outside Docker):
   ```bash
   # macOS / Linux
   export UV_PROJECT_ENVIRONMENT=venvAO03 && uv sync --frozen
   ```
   ```powershell
   # Windows PowerShell
   $env:UV_PROJECT_ENVIRONMENT="venvAO03"; uv sync --frozen
   ```
3. **Keys**: copy `.env.example` to `.env` and fill in the same two keys as Session 01 (`OPENAI_API_KEY`,
   `TAVILY_API_KEY`). Copy `.env.db.example` to `.env.db` and choose a password. Both files are in `.gitignore`
   and `.dockerignore`: they never enter git or an image.
4. **Check**: `uv run pytest -q` → `23 passed` (no key, no Docker needed).

Demo users (`data/users.json`): `alice-dev-token` → alice, `bob-dev-token` → bob. Set two variables for the curl
commands:
```bash
API=http://localhost:8000
ALICE="Authorization: Bearer alice-dev-token"
```
If port 8000 is taken on your machine, publish another host port (`-p 8003:8000`, or `API_PORT=8003` in `.env` for
Compose) and change `API` to match; the container always listens on 8000.

## Lab (≈ 60 min: core 50 min + extension 10 min)

| Time | Part | Who |
|---|---|---|
| 0–10 | 1. **Challenge 1**: the first Dockerfile, run it, the `fastapi dev` trap | you → instructor |
| 10–22 | 2. **Challenge 2**: cache order, `.dockerignore`, multi-stage, non-root; measure | you → instructor |
| 22–30 | 3. **Challenge 3**: keys at run time; bake a **fake** key and find it | you → instructor |
| 30–37 | 4. **Challenge 4**: `HEALTHCHECK`, exec form vs shell form on `docker stop` | you → instructor |
| 37–50 | 5. **Challenge 5**: Compose with Postgres; down/up; break it three ways | you + class |
| 50–60 | Extension: `docker compose watch`, `--platform linux/amd64`, `/ready` without the database, the UI | optional |

All numbers below were measured on one Linux x86_64 machine (Docker 29.2.1); yours will differ, the order of
magnitude should not.

### 1. Challenge 1 — the first Dockerfile (10 min)

Write the simplest Dockerfile that works (`Dockerfile.naive`):
```dockerfile
FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install uv && uv sync
EXPOSE 8000
CMD ["uv", "run", "fastapi", "run"]
```
```bash
docker build -f Dockerfile.naive -t agent-api:naive .
docker run -d --name naive --env-file .env -p 8000:8000 agent-api:naive
curl -s -i $API/health
```
Real output:
```
HTTP/1.1 200 OK
...
{"status":"ok"}
```
Container log: `🌐 Server started at http://0.0.0.0:8000` and
`agent ready in 182 ms: model=openai:gpt-6-luna prompt_sha256=439f527b5660 checkpointer=memory`.
`docker exec naive whoami` → `root`. Stop it: `docker rm -f naive`.

**The `fastapi dev` trap.** Run the same image with the development server:
```bash
docker run -d --name devtest --env-file .env -p 8000:8000 agent-api:naive uv run fastapi dev
curl -s $API/health
```
```
curl: (56) Recv failure: Connection reset by peer
```
The log says `Uvicorn running on http://127.0.0.1:8000`: inside a container, 127.0.0.1 is the container itself, so the
published port reaches nobody. `fastapi run` listens on `0.0.0.0`. (`docker rm -f devtest`.)

Sizes (`docker image ls`; Docker 29 shows the disk usage and the compressed content size):
```
IMAGE              ID             DISK USAGE   CONTENT SIZE
python:3.12        17b9724493d9       1.62GB          430MB
python:3.12-slim   aa943ce41142        179MB         45.5MB
agent-api:naive    c29ae53d66dc        1.9GB          486MB
```

### 2. Challenge 2 — cache, .dockerignore, multi-stage, non-root (12 min)

Read `Dockerfile` from top to bottom. Four ideas:
- **Dependencies before code.** `COPY pyproject.toml uv.lock ./` then `uv sync --locked --no-install-project`, and only
  then `COPY . .` and `uv sync --locked`. A code change rebuilds from `COPY . .`; the dependency layer stays cached.
- **uv from a pinned image** (`COPY --from=ghcr.io/astral-sh/uv:0.13.6 …`), a cache mount for uv's download cache,
  `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`, `UV_NO_DEV=1`. The base image is pinned by **digest**.
- **Multi-stage.** The `runtime` stage starts again from `python:3.12-slim` and copies only `/app` (code + `.venv`).
- **Non-root.** `useradd app`, `COPY --chown=app:app`, `USER app`.

```bash
docker build -t agent-api:0.3.0 .
docker run --rm agent-api:0.3.0 whoami          # app
```
Change one line in `src/research_assistant/agent/agent.py` and build again with `--progress=plain`. Real output
(the steps that matter):
```
#13 [build 5/7] RUN --mount=type=cache,target=/root/.cache/uv     uv sync --locked --no-install-project
#13 CACHED
#14 [build 6/7] COPY . .
#14 DONE 0.0s
#15 [build 7/7] RUN --mount=type=cache,target=/root/.cache/uv     uv sync --locked
#15 0.118 Prepared 1 package in 6ms
#15 0.206  + research-assistant==0.3.0 (from file:///app)
```
Only the project itself is reinstalled. Now measure both Dockerfiles with the script (it warms the cache, appends one
line to `agent.py`, times the rebuild, restores the file):
```bash
scripts/measure_rebuild.sh Dockerfile.naive agent-api:naive
scripts/measure_rebuild.sh Dockerfile agent-api:0.3.0
```
```
rebuild of agent-api:naive (Dockerfile.naive) after a one-line change:
182.469 s
IMAGE             ID             DISK USAGE   CONTENT SIZE
agent-api:naive   c29ae53d66dc        1.9GB          486MB
rebuild of agent-api:0.3.0 (Dockerfile) after a one-line change:
8.436 s
IMAGE             ID             DISK USAGE   CONTENT SIZE
agent-api:0.3.0   c70bfa66b6ab        439MB         93.7MB
```
Real results (two runs each; cold builds with `docker build --no-cache`):

| | `Dockerfile.naive` | `Dockerfile` (multi-stage) |
|---|---|---|
| Base image | `python:3.12` (1.62GB / 430MB) | `python:3.12-slim` (179MB / 45.5MB) |
| Cold build (`--no-cache`) | 38.8 s | 41.1 s |
| Rebuild after a one-line code change | 155.4 s, 182.5 s | 8.30 s, 8.44 s |
| Image size (disk / content) | 1.9GB / 486MB | 439MB / 93.7MB |
| User | root | app |

The naive rebuild is **slower than its cold build**: `COPY . .` comes before `pip install uv && uv sync`, so a code
change throws away the dependency layer and every package is downloaded again (no cache mount), and the time depends on
the network. In the multi-stage build the 93 packages are installed once.

**What `.dockerignore` keeps out.** `breaks/Dockerfile.context` copies the whole build context into an image:
```bash
docker build --progress=plain -f breaks/Dockerfile.context -t ctx-with .
docker run --rm ctx-with sh -c 'du -sh /ctx; ls /ctx/.env'
```
Then move `.dockerignore` away, build `ctx-without` the same way, and put `.dockerignore` back. Real results (in a copy
of this folder with a **fake** `.env` and the `venvAO03` environment):

| | with `.dockerignore` | without |
|---|---|---|
| `transferring context` | 297.44kB | 157.91MB |
| `du -sh /ctx` | 516K | 174M (the virtual environment) |
| `/ctx/.env` | `No such file or directory` | `OPENAI_API_KEY=sk-FAKE-context-demo` |
| Image size | 178MB | 403MB |

Without `.dockerignore`, `COPY . .` puts your `.env` into a layer of the image.

### 3. Challenge 3 — keys and config at run time (8 min)

The image contains no key. Keys and settings arrive when the container starts:
```bash
docker run -d --name agent-api --env-file .env -e APP_ENV=prod -p 8000:8000 agent-api:0.3.0
curl -s $API/health; echo; curl -s $API/ready; echo; curl -s $API/v1/info -H "$ALICE"
```
Real output:
```
{"status":"ok"}
{"status":"ready","checks":{"agent":"ok","sessions":"ok","accepting":"ok"}}
{"service":"research-assistant","version":"0.3.0","app_env":"prod","model":"openai:gpt-6-luna","prompt_sha256":"439f527b5660"}
```
Log line: `agent ready in 68 ms: model=openai:gpt-6-luna prompt_sha256=439f527b5660 checkpointer=memory`.
Open http://localhost:8000/ui/ and send a question: the UI of Session 02, now served from the container.

Check that the image holds no key:
```bash
docker history --no-trunc agent-api:0.3.0 | grep -c API_KEY                  # 0
docker image inspect agent-api:0.3.0 --format '{{json .Config.Env}}'
```
```
["PATH=/app/.venv/bin:/usr/local/bin:…","LANG=C.UTF-8","GPG_KEY=7169605F…","PYTHON_VERSION=3.12.16","PYTHON_SHA256=b5796915…"]
```
(`GPG_KEY` is the public key the Python image uses to verify its download, not a secret.)

**Break it — with a FAKE key only.** Never use a real key for this step.
```bash
docker build -f breaks/Dockerfile.leak --build-arg OPENAI_API_KEY=sk-FAKE-for-the-leak-demo-000 -t leak-demo breaks
docker history --no-trunc --format '{{.CreatedBy}}' leak-demo | head -2
docker image inspect leak-demo --format '{{json .Config.Env}}'
```
Real output:
```
 - SecretsUsedInArgOrEnv: Do not use ARG or ENV instructions for sensitive data (ARG "OPENAI_API_KEY") (line 4)
 - SecretsUsedInArgOrEnv: Do not use ARG or ENV instructions for sensitive data (ENV "OPENAI_API_KEY") (line 5)
ENV OPENAI_API_KEY=sk-FAKE-for-the-leak-demo-000
ARG OPENAI_API_KEY=sk-FAKE-for-the-leak-demo-000
[…,"PYTHON_SHA256=b5796915…","OPENAI_API_KEY=sk-FAKE-for-the-leak-demo-000"]
```
Anyone who can pull the image can read the key. A key that has been in an image must be **revoked**, not just removed
from the Dockerfile. Clean up: `docker rmi leak-demo`.

### 4. Challenge 4 — health check and graceful shutdown (7 min)

The `HEALTHCHECK` calls `/health` with the Python that is already in the image (the slim image has no curl). With the
container from Part 3 running:
```bash
docker ps --format '{{.Names}}  {{.Status}}'
```
```
agent-api  Up 34 seconds (healthy)
```
Now `docker stop` it, then compare the exec form `CMD ["fastapi", "run"]` with the shell form `CMD fastapi run`:
```bash
docker logs agent-api 2>&1 | tail -4; docker rm agent-api
scripts/measure_stop.sh agent-api:0.3.0
```
Real output:
```
INFO:     Waiting for application shutdown.
04:19:07 INFO research_assistant.api request_id=- user_id=- session_id=- | shutdown complete: checkpointer=memory
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
PID 1 (exec form): /app/.venv/bin/python /app/.venv/bin/fastapi run
docker stop (exec form): 0.471 s
exit code (exec form): 0
PID 1 (shell form): /bin/sh -c fastapi run
docker stop (shell form): 10.121 s
exit code (shell form): 137
```

| `CMD` | PID 1 | `docker stop` | Exit code | Lifespan shutdown runs |
|---|---|---|---|---|
| exec form `["fastapi", "run"]` | fastapi | 0.471 s | 0 | yes |
| shell form `fastapi run` | `/bin/sh` | 10.121 s | 137 (SIGKILL) | no |

`/bin/sh` does not forward SIGTERM to its child, so Docker waits its 10-second grace period and kills everything.

**Discussion:** `docker ps` says `(healthy)`, yet the agent can still fail every run (wrong OpenAI key). What does the
health check prove, and what does `/ready` add? Docker itself only *reports* `unhealthy`; it does not restart the
container.

### 5. Challenge 5 — the agent and Postgres with Docker Compose (13 min)

Read `compose.yaml`: `agent-api` is built from the `Dockerfile`, gets its keys from `.env` and the database user from
`.env.db`, finds Postgres at `DB_HOST: postgres` (the service name) and starts only when `postgres` is
`service_healthy` (`pg_isready`). Data lives in the named volume `pgdata`. With `CHECKPOINTER=postgres`, the lifespan
opens a connection pool, creates the LangGraph checkpoint tables (`AsyncPostgresSaver.setup()`) and the `sessions`
table.

```bash
docker compose up -d --build
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
curl -s $API/ready
```
Real output:
```
 Container 03_docker-postgres-1 Waiting
 Container 03_docker-postgres-1 Healthy
 Container 03_docker-agent-api-1 Starting
 Container 03_docker-agent-api-1 Started
SERVICE     STATUS
agent-api   Up 3 minutes (healthy)
postgres    Up 5 minutes (healthy)
{"status":"ready","checks":{"agent":"ok","sessions":"ok","accepting":"ok","database":"ok"}}
```
Stream a run (same as Session 02):
```bash
SID=$(curl -s -X POST $API/v1/sessions -H "$ALICE" | uv run python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST $API/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
```
Real output (shortened):
```
event: metadata
data: {"run_id": "6920d670", "session_id": "51bbd9e5-cd73-4a91-9c20-b1d8430d5402"}
...
event: done
data: {"status": "completed", "answer": "- In cold-climate studies, seasonal COPs have been about **2.5–3.1** … about **3,900–4,800 kWh of electricity** (12,000 ÷ COP) …", "seconds": 63.8, "model_calls": 10, "input_tokens": 38905, "output_tokens": 1523}
```
**Down, up, read the session again:**
```bash
docker compose down && docker compose up -d
curl -s $API/v1/sessions/$SID -H "$ALICE"
curl -s -i $API/v1/sessions/$SID -H "Authorization: Bearer bob-dev-token"
docker compose exec postgres psql -U agent -c '\dt'
```
Real output (a short run, messages shortened to their role and length):
```
{'session_id': '79143499-c4b7-4ae2-949c-e42bfdf3d7b8', 'title': 'What is 12000 / 2.5? Use the calculator.', 'created_at': '2026-11-02T04:22:01.095227Z', 'messages': [('user', 40), ('assistant', 86)]}
HTTP/1.1 404 Not Found
{"type":"about:blank","title":"Not Found","status":404,"detail":"Session 79143499-c4b7-4ae2-949c-e42bfdf3d7b8 not found",…}
 Schema |         Name          | Type  | Owner
--------+-----------------------+-------+-------
 public | checkpoint_blobs      | table | agent
 public | checkpoint_migrations | table | agent
 public | checkpoint_writes     | table | agent
 public | checkpoints           | table | agent
 public | sessions              | table | agent
```
The containers were deleted, the volume was not: alice's session and its messages are still there; bob still gets 404.

**Break it three ways** (read the answer each time, then `docker compose down` and `up -d` again):
1. **`localhost` instead of the service name:**
   `docker compose -f compose.yaml -f breaks/compose.localhost.yaml up -d`, then `docker compose logs agent-api`:
   ```
   error connecting in 'pool-1': connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
   psycopg_pool.PoolTimeout: pool initialization incomplete after 10 sec
   ERROR:    Application startup failed. Exiting.
   ```
   `docker compose ps -a` shows `agent-api … Exited (3)`. In a container, `localhost` is the container itself.
2. **No `service_healthy`:** `docker compose down -v && docker compose -f compose.yaml -f breaks/compose.no-healthy.yaml up -d`.
   On the reference machine the service still started (`agent ready in 99 ms`): `pool.open(wait=True, timeout=10)`
   keeps retrying for 10 s, which covered Postgres' first start. Without the pool's wait (or on a slower machine) the
   agent starts before the database accepts connections. `service_healthy` makes the order explicit instead of lucky.
3. **`down -v`:** `docker compose down -v && docker compose up -d`, then read the old session:
   ```
   {"type":"about:blank","title":"Not Found","status":404,"detail":"Session … not found",…}
   ```
   `-v` deletes the named volume, and with it every session.

### Extension (10 min, optional)

- **`docker compose watch`.** `compose.yaml` has a `develop.watch` block: `sync+restart` for `./src`, `rebuild` for
  `pyproject.toml` and `uv.lock`. Run `docker compose watch`, wait for `Watch enabled`, edit
  `api/routers/health.py`; real log:
  ```
  Watch enabled
  Syncing service "agent-api" after 2 changes were detected
  service(s) ["agent-api"] restarted
  ```
  `curl $API/health` shows the change without `docker compose up --build`. Revert the edit; it syncs back.
- **`--platform linux/amd64`.** Cloud Run runs `linux/amd64` images. Build for it and read the architecture:
  ```bash
  docker build --platform linux/amd64 -t agent-api:0.3.0-amd64 .
  docker image inspect agent-api:0.3.0-amd64 --format '{{.Os}}/{{.Architecture}}'    # linux/amd64
  ```
  On an x86_64 machine this is the native platform (12.8 s with a warm cache). On Apple Silicon the build runs under
  emulation and is slower; try it before Session 04.
- **`/ready` without the database.** `docker compose stop postgres`, then:
  `curl -i $API/ready` → `503` with `{"status":"not ready","checks":{…,"database":"unreachable"}}`, while `curl $API/health` stays `200`.
  `docker compose start postgres` and `/ready` returns to 200 (the pool checks each connection before use and replaces
  the broken ones). `docker compose restart postgres` restarts `agent-api` too (`restart: true` under `depends_on`).
- **The UI through the container.** http://localhost:8000/ui/ against the Compose stack, question "What is 12000 / 2.5?":
  header `v0.3.0 · openai:gpt-6-luna · prompt 439f527b5660`, activity `run started | model answered | call calculate |
  tools ran | result calculate success: 4800.0 | model answered`, answer `12,000 ÷ 2.5 = 4,800.`, footer
  `done in 5 s · 2 model calls · 363 input / 45 output tokens`.

### Tests and baseline

```
$ uv run pytest -q
.......................                                                  [100%]
23 passed
```
`tests/test_docker_files.py` checks the Docker files: exec-form `CMD`, `USER app`, `.env` in `.dockerignore`,
`DB_HOST: postgres` and `service_healthy` in `compose.yaml`. The Session 01 baseline still runs from this folder
(`uv run research-assistant --baseline`); two runs of v0.3.0 are in `baselines/v0.3.0/` (36.7 s and 25.7 s, 5 and 6
model calls).

## Troubleshooting

- `failed to bind host port 0.0.0.0:8000/tcp: address already in use`: another process uses port 8000. Publish another
  host port (`-p 8003:8000`, or `API_PORT=8003` in `.env` for Compose) and set `API` to match.
- `curl: (56) Recv failure: Connection reset by peer`: the server in the container listens on 127.0.0.1
  (`fastapi dev`). Use `fastapi run` (0.0.0.0).
- `docker stop` takes 10 s and the exit code is 137: the `CMD` is in shell form; use the exec form `["fastapi", "run"]`.
- `PoolTimeout: pool initialization incomplete after 10 sec` with `connection to server at "127.0.0.1", port 5432 … refused`:
  `DB_HOST` is `localhost`; inside Compose it must be the service name `postgres`.
- `SecretsUsedInArgOrEnv` warning while building: a key is passed with `ARG`/`ENV`. Pass it at run time.
- `Invalid settings` at start-up: `.env` is missing or a key is empty; `docker run` needs `--env-file .env`.
- Windows PowerShell: use `curl.exe`, and `$env:API="http://localhost:8000"`.

## References

- Docker: Dockerfile reference https://docs.docker.com/reference/dockerfile/ · Build cache
  https://docs.docker.com/build/cache/ · Multi-stage builds https://docs.docker.com/build/building/multi-stage/ ·
  Build context and `.dockerignore` https://docs.docker.com/build/concepts/context/
- Build secrets https://docs.docker.com/build/building/secrets/ · `SecretsUsedInArgOrEnv`
  https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/ · `docker image history`
  https://docs.docker.com/reference/cli/docker/image/history/
- uv in Docker: https://docs.astral.sh/uv/guides/integration/docker/ · FastAPI in containers
  https://fastapi.tiangolo.com/deployment/docker/ · FastAPI CLI https://fastapi.tiangolo.com/fastapi-cli/
- `docker stop` https://docs.docker.com/reference/cli/docker/container/stop/ · `HEALTHCHECK`
  https://docs.docker.com/reference/dockerfile/#healthcheck
- Compose: file reference https://docs.docker.com/reference/compose-file/ · startup order
  https://docs.docker.com/compose/how-tos/startup-order/ · file watch https://docs.docker.com/compose/how-tos/file-watch/
- Postgres image https://hub.docker.com/_/postgres · LangGraph persistence
  https://docs.langchain.com/oss/python/langgraph/persistence · psycopg pool
  https://www.psycopg.org/psycopg3/docs/advanced/pool.html
- Multi-platform images https://docs.docker.com/build/building/multi-platform/ · Cloud Run container contract
  https://cloud.google.com/run/docs/container-contract
