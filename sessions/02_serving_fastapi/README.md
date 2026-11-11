# Session 02 — Serving the Agent with FastAPI

## Goal

In Session 01 the research agent became a package you run with `uv run research-assistant "…"`. Today it becomes an
**HTTP service** that many users and clients can call: a FastAPI app with a versioned API (`/v1`), one session per
conversation, each run **streamed as Server-Sent Events** (steps, tool calls, tokens, result), a minimal browser UI,
`/health` and `/ready` for the platform, one error format, and application logs where every line carries a
`request_id`. Session 03 packages exactly this service in Docker; Session 04 deploys it to Cloud Run.

The agent itself does not change (same model, prompt and tools as Session 01); only the way it is served does.

## What is in this folder

```
02_serving_fastapi/
  src/research_assistant/
    api/                 HTTP only
      main.py            app, lifespan (start-up/shutdown), request_id middleware, CORS, routers, /ui
      deps.py            dependencies: settings, current user (bearer token), agent, session ownership
      errors.py          one error body for every failure (RFC 9457 Problem Details)
      routers/           health.py (/health, /ready) · info.py · sessions.py · runs.py (SSE)
    schemas/             the API contract: RunRequest, Session, Info, Problem (Pydantic)
    services/sessions.py which user owns which session (in memory)
    agent/               the agent runtime; never imports FastAPI
      agent.py           build_agent(), ask() (Session 01 CLI), prompt_sha256()
      events.py          LangGraph stream -> step / tool_call / tool_result / token / done
      tools.py           web_search, calculate (Session 01)
      prompts/system_prompt.md
    core/                config.py (Settings) · logging.py (request_id on every log line)
    __main__.py          the Session 01 CLI, unchanged: uv run research-assistant "…"
    baseline.py          the Session 01 baseline
  static/                the demo UI (index.html, app.js, app.css): fetch() + ReadableStream
  tests/                 offline API tests with a fake agent (no key, no network)
  payloads/              request bodies to try, including invalid ones
  examples/              extension: blocking_demo.py + concurrent_requests.py
  data/users.json        demo bearer tokens (alice, bob)
  baselines/  pyproject.toml  uv.lock  .python-version  .env.example  .gitignore
```

The folder is the **answer key**. Keep working in **your own repository** from Session 01 (outside
`agentops_bootcamp/`), on a branch `serve-api`, and compare with this folder after each challenge.

## Setup (in this folder)

1. **Create the environment**:
   ```bash
   # macOS / Linux
   export UV_PROJECT_ENVIRONMENT=venvAO02 && uv sync --frozen
   ```
   ```powershell
   # Windows PowerShell
   $env:UV_PROJECT_ENVIRONMENT="venvAO02"; uv sync --frozen
   ```
   Keep this terminal: every later `uv run` uses `venvAO02`.
2. **Keys**: copy `.env.example` to `.env` (same folder) and fill in the same two keys as Session 01:
   - `OPENAI_API_KEY`: https://platform.openai.com/api-keys → *Create new secret key*.
   - `TAVILY_API_KEY`: https://app.tavily.com → *API Keys*.
3. **Check**: `uv run pytest -q` → `21 passed` (no key needed), then `uv run research-assistant --show-config`
   shows both keys as `**********`.
4. **IDE**: open **this folder** in VS Code or Cursor. `curl` must work in your terminal (`curl --version`);
   on Windows use `curl.exe` in PowerShell.

## Run the service

```bash
uv run fastapi dev        # development: reloads on every file save, listens on 127.0.0.1:8000
```
Real output (start of it):
```
 ⚡️ Starting FastAPI in development mode
 🐍 Using import string: research_assistant.api.main:app
 🌐 Server started at http://127.0.0.1:8000
    Documentation at http://127.0.0.1:8000/docs
...
11:11:37 INFO research_assistant.api request_id=- user_id=- session_id=- | agent ready in 90 ms: model=openai:gpt-6-luna prompt_sha256=439f527b5660
INFO:     Application startup complete.
```
`[tool.fastapi] entrypoint` in `pyproject.toml` tells the CLI where the app is. Then open:
- http://127.0.0.1:8000/docs — Swagger UI generated from the code (*Authorize* → `alice-dev-token`);
- http://127.0.0.1:8000/ui/ — the demo UI: press **Send** and watch the run activity and the answer arrive.

Demo users (`data/users.json`): `alice-dev-token` → alice, `bob-dev-token` → bob.

## Lab (≈ 75 min: core 60 min + extension 15 min)

| Time | Part | Who |
|---|---|---|
| 0–5 | 1. Run the service, open `/docs` and `/ui/` | you |
| 5–17 | 2. **Challenge 1** (8 min): request/response schemas; live-code (4 min) | you → instructor |
| 17–32 | 3. **Challenge 2** (10 min): `/v1` router, three dependencies, `lifespan`; live-code (5 min) | you → instructor |
| 32–44 | 4. **Challenge 3** (8 min): the streaming run endpoint and `/v1/info`; live-code (4 min) | you → instructor |
| 44–54 | 5. **Challenge 4** (7 min): `request_id` middleware, error handlers, `/health`, `/ready`; live-code (3 min) | you → instructor |
| 54–60 | 6. Break the API, read every answer; discussion question | you + class |
| 60–75 | Extension: **Challenge 5** (a test with `dependency_overrides`), the blocking demo, CORS | optional |

Every command below runs in a second terminal while `uv run fastapi dev` runs in the first. Set two variables first:
```bash
API=http://127.0.0.1:8000
ALICE="Authorization: Bearer alice-dev-token"
```

### 1. Run the service (5 min)

Start the server (above), open `/docs` and `/ui/`, send the prefilled question from the UI. A run takes 20–45 s
(4–9 model calls); the first tool call shows after about 2 s, the answer text only at the end.

### 2. Challenge 1 — schemas (8 min + 4 min live-code)

In `src/research_assistant/schemas/` write the contract with Pydantic:
- `RunRequest`: `message: str` with `min_length=1`, `max_length=2000`, and `extra="forbid"` (an unknown field is an
  error, so nobody can pass `user_id` in the body);
- `Session` (`session_id`, `title`, `created_at`) and `Info` (`service`, `version`, `app_env`, `model`, `prompt_sha256`);
- `Problem`: the error body (`type`, `title`, `status`, `detail`, `instance`, `request_id`).

Check against `schemas/sessions.py` and `schemas/system.py`. Routes declare the return type (`-> Session`), so FastAPI
validates and filters what leaves the service.

### 3. Challenge 2 — router, dependencies, lifespan (10 min + 5 min live-code)

- `api/deps.py`: three dependencies, each used as an `Annotated[..., Depends(...)]` alias:
  `get_settings` (cached with `@lru_cache`), `get_current_user` (reads `Authorization: Bearer …`, 401 otherwise) and
  `get_agent` (returns `request.app.state.agent`). Add `get_owned_session`: the session must belong to the user, else 404.
- `api/main.py`: a `lifespan` that builds the agent **once** (`build_agent(settings, InMemorySaver())`), the session
  store and `app.state.info`; one `APIRouter(prefix="/v1", dependencies=[Depends(get_current_user)])` that includes
  `info`, `sessions` and `runs`.
- Keep `agent/` free of FastAPI imports: the test `test_agent_layer_does_not_import_fastapi` checks it.

```bash
curl -s -X POST $API/v1/sessions -H "$ALICE"
```
```
{"session_id":"dadca431-dac0-48bf-811c-f9679ce9e3fd","title":"New session","created_at":"2026-11-02T03:43:56.554286Z"}
```

### 4. Challenge 3 — stream a run, serve /v1/info (8 min + 4 min live-code)

`api/routers/runs.py`: `POST /v1/sessions/{session_id}/runs` with `response_class=EventSourceResponse`; the function
is an async generator that yields `ServerSentEvent(event=…, data=…, id=…)`: first `metadata`, then the events of
`agent/events.py`, last `done` (or `error`). `GET /v1/info` returns `app.state.info`.

```bash
SID=$(curl -s -X POST $API/v1/sessions -H "$ALICE" | uv run python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -i -X POST $API/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
```
Real output (`-N` prints each event as it arrives; shortened):
```
HTTP/1.1 200 OK
content-type: text/event-stream; charset=utf-8
cache-control: no-cache
x-accel-buffering: no
x-request-id: 971956f334e3

event: metadata
data: {"run_id": "73a05a4a", "session_id": "7b6f9e30-58a7-4936-bbac-cfebf5cc6394"}
id: 73a05a4a-1

event: step
data: {"node": "model"}
id: 73a05a4a-2

event: tool_call
data: {"id": "call_o9OT…", "name": "web_search", "args": {"query": "air source heat pump cold climate seasonal COP …"}}
id: 73a05a4a-3
...
event: done
data: {"status": "completed", "answer": "- A Minnesota field study reported … annual COPs of **2.51–2.78** …", "seconds": 24.5, "model_calls": 6, "input_tokens": 6901, "output_tokens": 563}
id: 73a05a4a-114
```
```bash
curl -s $API/v1/info -H "$ALICE"
```
```
{"service":"research-assistant","version":"0.2.0","app_env":"dev","model":"openai:gpt-6-luna","prompt_sha256":"439f527b5660"}
```
`prompt_sha256` is the same value the Session 01 baseline manifest stores, so a log line or a bug report can be tied
to the exact release.

### 5. Challenge 4 — request_id, errors, health (7 min + 3 min live-code)

- A middleware (`@app.middleware("http")`) gives every request an id (kept from an incoming `X-Request-ID` header if
  it is safe, else a new one), returns it in the `X-Request-ID` response header and logs one line per request.
- `core/logging.py` puts `request_id`, `user_id` and `session_id` on **every** log line (a `logging.Filter` reading
  context variables), printed to stdout.
- `api/errors.py`: handlers turn `HTTPException` and validation errors into one `application/problem+json` body that
  includes the `request_id`.
- `/health` answers 200 while the process runs; `/ready` answers 503 when a run cannot succeed now. Here it checks
  that the agent is built and that the provider accepts the key for the model (`check_model`: a metadata call, no tokens,
  cached 30 s).

The server log of one run (real; long ids shortened):
```
11:01:07 INFO research_assistant.api.routers.runs request_id=24c20c00023b user_id=alice session_id=d780a347-… | run 21b3571f started: message_chars=155
11:01:07 INFO research_assistant.api request_id=24c20c00023b user_id=alice session_id=- | POST /v1/sessions/d780a347-…/runs -> 200 (6 ms)
11:01:14 INFO research_assistant.agent.tools request_id=24c20c00023b user_id=alice session_id=d780a347-… | web_search -> 3 results
11:01:16 INFO research_assistant.agent.tools request_id=24c20c00023b user_id=alice session_id=d780a347-… | calculate(12000 / 2.5) -> 4800.0
...
11:01:44 INFO research_assistant.api.routers.runs request_id=24c20c00023b user_id=alice session_id=d780a347-… | run 21b3571f completed in 36.8 s: model_calls=5 input_tokens=9336 output_tokens=828
```
The middleware line says `200 (6 ms)`: for a stream, the response *starts* after 6 ms; the run line gives the real
duration. The question text is not logged (only its length).

### 6. Break the API (6 min)

Send each payload and read the answer: status, `errors[].loc`, `errors[].type`.
```bash
for f in run_empty_message run_wrong_type run_user_id_in_body run_wrong_field run_too_long; do
  curl -s -X POST $API/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/$f.json; echo
done
```
Real answers (`errors` only):

| Payload | Status | `errors` |
|---|---|---|
| `{"message": ""}` | 422 | `["body","message"]` `string_too_short` |
| `{"message": 42}` | 422 | `["body","message"]` `string_type` |
| `{"message": "…", "user_id": "bob"}` | 422 | `["body","user_id"]` `extra_forbidden` |
| `{"question": "…"}` | 422 | `["body","message"]` `missing` + `["body","question"]` `extra_forbidden` |
| 2,001 characters | 422 | `["body","message"]` `string_too_long` |

Then:
- **Someone else's session**: `curl -i $API/v1/sessions/$SID -H "Authorization: Bearer bob-dev-token"` →
  `404 Not Found`, the same answer as for a session that does not exist. Running on it is refused before any stream starts.
- **Wrong session id**: `curl -s $API/v1/sessions/me -H "$ALICE"` → 422
  `"Input should be a valid UUID, invalid character: found 'm' at 0"`, `type: uuid_parsing`: the path matched
  `/v1/sessions/{session_id}`. A route `/v1/sessions/me` would have to be declared **before** that one. `tests/test_route_order.py` shows both orders: `/me` declared after `/{session_id}` → 422, declared first → 200.
- **No token**: `401 Unauthorized`, header `www-authenticate: Bearer`.
- **Close the client mid-stream**: `timeout 4 curl -N -X POST …/runs …` (or close the UI tab during a run). Server log:
  ```
  10:47:47 WARNING research_assistant.api.routers.runs request_id=6ac4862283cc … | run 3549ccb3 cancelled after 4.0 s
  10:47:49 INFO research_assistant.agent.tools request_id=6ac4862283cc … | web_search -> 3 results
  ```
  No model call follows; the web search that was already running in a worker thread still finishes.
- **A run that is too slow**: restart with `RUN_TIMEOUT_S=3 uv run fastapi dev` and run again. The status is already
  200, so the failure arrives as an event:
  ```
  event: error
  data: {"type": "about:blank", "title": "Gateway Timeout", "status": 504, "detail": "The run took too long and was stopped.", "instance": "/v1/sessions/fe237d59-…/runs", "request_id": "52f5cf5db08d"}
  ```

**Discussion:** why can `/ready` answer 503 while `/health` still answers 200? Try it:
```bash
OPENAI_API_KEY=sk-invalid-demo-key uv run fastapi dev
curl -i $API/health      # HTTP/1.1 200 OK            {"status":"ok"}
curl -i $API/ready       # HTTP/1.1 503 Service Unavailable
                         # {"status":"not ready","checks":{"agent":true,"model":false}}
```
The process is alive (restarting it would not fix a revoked key), but every run would fail with `event: error` status
502, so the platform should stop sending it traffic. Other real cases: a database the service needs is unreachable, the provider quota is used up.

### Extension (15 min, optional)

- **Challenge 5 — a test without the model (7 min).** Read `tests/conftest.py`: `FakeAgent.astream` replays the
  shape of a real run; `app.dependency_overrides[get_agent] = lambda: fake` swaps it in. Write one more test, for
  example "an unknown token gets 401 on `POST /v1/sessions`". Real output:
  ```
  $ uv run pytest -q
  .....................                                                    [100%]
  21 passed in 0.34s
  ```
- **A blocking call inside `async def` (5 min).**
  ```bash
  uv run fastapi run examples/blocking_demo.py --port 8020      # terminal 1
  uv run python examples/concurrent_requests.py                 # terminal 2
  ```
  Real output:
  ```
  /async-blocking  5 requests: each 1.0 2.0 3.0 4.0 5.0 s | all done in 5.0 s
  /async-awaiting  5 requests: each 1.0 1.0 1.0 1.0 1.0 s | all done in 1.0 s
  /sync            5 requests: each 1.0 1.0 1.0 1.0 1.0 s | all done in 1.0 s
  ```
  `time.sleep` inside `async def` blocks the event loop, so the five requests wait for each other. The service calls
  the agent with `astream` (awaitable), never `invoke`.
- **CORS (3 min).** Serve the UI from another origin and call the API from it:
  ```bash
  uv run python -m http.server 5500 -d static
  ```
  Open http://localhost:5500/?api=http://127.0.0.1:8000 — the browser console shows
  `… has been blocked by CORS policy: Response to preflight request doesn't pass access control check: No
  'Access-Control-Allow-Origin' header is present on the requested resource.` Set
  `CORS_ORIGINS=["http://localhost:5500"]` in `.env`, restart the server, reload: the run works and DevTools →
  Network shows the `OPTIONS` preflight answered with `access-control-allow-origin: http://localhost:5500`.
- **Two worker processes.** `uv run fastapi run --workers 2`, create a session, then read it ten times: real result
  `200 404 404 200 404 404 200 404 404 404`. Sessions live in one process's memory; the other worker does not know
  them. Serve this version with one worker; a shared store (a database) comes later in the course.

## Troubleshooting

- `ERROR: [Errno 98] … address already in use`: another server uses the port. Use `uv run fastapi dev --port 8002`
  (and `API=http://127.0.0.1:8002`).
- `Invalid settings` / `ValidationError … openai_api_key` at start-up: `.env` is missing in this folder or a key is empty.
- `{"detail": …}` instead of a problem body, or `401` on `/v1/...`: the `Authorization: Bearer <token>` header is
  missing or the token is not in `data/users.json`.
- The UI shows `TypeError: Failed to fetch` when opened from another port: CORS (see the extension).
- `curl` prints the whole stream at the end: add `-N` (no buffering). Behind Nginx, the `X-Accel-Buffering: no`
  header that FastAPI sets stops the proxy from buffering.
- Windows PowerShell: use `curl.exe`, and `$env:API="http://127.0.0.1:8000"`.

## References

- FastAPI: First Steps https://fastapi.tiangolo.com/tutorial/first-steps/ · FastAPI CLI
  https://fastapi.tiangolo.com/fastapi-cli/ · Bigger Applications
  https://fastapi.tiangolo.com/tutorial/bigger-applications/
- Path/query parameters, body, `Field`: https://fastapi.tiangolo.com/tutorial/body-fields/ · response model
  https://fastapi.tiangolo.com/tutorial/response-model/ · handling errors https://fastapi.tiangolo.com/tutorial/handling-errors/
- Concurrency and async/await: https://fastapi.tiangolo.com/async/ · Dependencies:
  https://fastapi.tiangolo.com/tutorial/dependencies/ · Settings:
  https://fastapi.tiangolo.com/advanced/settings/ · Lifespan events: https://fastapi.tiangolo.com/advanced/events/
- Middleware: https://fastapi.tiangolo.com/tutorial/middleware/ · CORS: https://fastapi.tiangolo.com/tutorial/cors/ ·
  Testing: https://fastapi.tiangolo.com/tutorial/testing/ · Testing dependencies with overrides:
  https://fastapi.tiangolo.com/advanced/testing-dependencies/
- Server-Sent Events in FastAPI: https://fastapi.tiangolo.com/tutorial/server-sent-events/ · MDN Using server-sent
  events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- RFC 9457 Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457 · The Twelve-Factor App, Logs:
  https://12factor.net/logs
