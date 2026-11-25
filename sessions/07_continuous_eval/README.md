# Session 04 — Deploying the Agent to Cloud Run

## Goal

In Session 03 the agent API became a Docker image that runs with Postgres under Docker Compose. Today the **same image**
runs on **Google Cloud**:
- it is pushed to **Artifact Registry** and deployed to **Cloud Run** by digest;
- it gets an HTTPS URL, probes and an instance cap;
- the keys, the database password and the token file come from **Secret Manager**;
- it runs as its own **service account** with two roles;
- sessions are stored in **Cloud SQL for PostgreSQL** through the `/cloudsql` Unix socket;
- you read its logs, roll back by moving traffic, check the cost and delete everything.

```
docker build ──► Artifact Registry ──► Cloud Run service agent-api ──► https://agent-api-….run.app
                 (tag + digest)          │ service account agent-api-runtime
                                         ├─► Secret Manager: openai-api-key, tavily-api-key, db-password, agent-users
                                         ├─► Cloud SQL agent-pg (PostgreSQL 18) via /cloudsql/PROJECT:us-central1:agent-pg
                                         └─► Cloud Logging (request logs + stdout)
```

The agent and the API do not change. There are two small code changes:
- the Dockerfile `HEALTHCHECK` reads `PORT`, because Cloud Run sets `PORT=8080` while Docker's default port is 8000;
- `/v1/info` returns `revision`, read from the `K_REVISION` variable that Cloud Run sets, so you can see which
  revision answered.

## What is in this folder

```
04_deploy_cloud/
  Dockerfile                  HEALTHCHECK follows PORT (was 127.0.0.1:8000)
  deploy/cloudrun.env.example new: PROJECT_ID and the names derived from it (no key)
  data/users.example.json     new: template of the token file uploaded to Secret Manager
  docs/cleanup.md             new: delete order and checks
  src/research_assistant/
    schemas/system.py         Info + revision
    api/main.py               revision = K_REVISION (None when run locally)
    …                         unchanged from Session 03
  compose.yaml  static/  tests/  payloads/  examples/  data/users.json  baselines/  pyproject.toml (0.4.0)  uv.lock
```

The folder is the **answer key**. Keep working in **your own repository** from Session 03, on a branch `cloud-run`.

## Before class

1. Do the Session 03 "next session" checklist:
   - a Google Cloud account and a project **with billing enabled**;
   - a **budget alert** (Billing → Budgets & alerts) with a low amount for the project;
   - the gcloud CLI installed (https://cloud.google.com/sdk/docs/install).
   New accounts get $300 of credit for 90 days. A budget only sends emails; it does not stop spending.
2. **Shell.** Every command below is bash. On Windows use **Git Bash** or **WSL**. If Docker does not run on your
   machine, use **Cloud Shell** (Console → *Activate Cloud Shell*): gcloud and Docker are installed there and you are
   already logged in. Upload this folder or `git clone` your repository there.
3. **Environment** (for the tests):
   ```bash
   export UV_PROJECT_ENVIRONMENT=venvAO04 && uv sync --frozen
   uv run pytest -q          # 25 passed (no key, no Docker, no cloud)
   ```
4. **Build the image for Cloud Run** (`linux/amd64`). A clean build takes minutes, so do it before class:
   ```bash
   docker build --platform linux/amd64 -t agent-api:0.4.0 .
   docker image inspect agent-api:0.4.0 --format '{{.Os}}/{{.Architecture}}'    # linux/amd64
   ```
5. **Variables.** Copy `deploy/cloudrun.env.example` to `deploy/cloudrun.env` and set `PROJECT_ID`. Load it in every
   new terminal:
   ```bash
   set -a && source deploy/cloudrun.env && set +a
   echo $IMAGE      # us-central1-docker.pkg.dev/<your project>/agentops/agent-api:0.4.0
   ```
   `deploy/cloudrun.env` and `secrets/` are in `.gitignore` and `.dockerignore`.

Names used everywhere: region `us-central1`, repository `agentops`, service `agent-api`, service account
`agent-api-runtime`, Cloud SQL instance `agent-pg` (database and user `agent`), secrets `openai-api-key`,
`tavily-api-key`, `db-password`, `agent-users`.

## Check the image locally first

These outputs were recorded with Docker 29.2.1 on a Linux x86_64 machine. Run them before you push.

**The image listens on the port that `PORT` names.** `fastapi run` reads `PORT` (default 8000) and binds 0.0.0.0, so
no code change is needed for Cloud Run. Fake keys are enough: the app only checks that they are set.
```
$ docker run -d --name b4run -e PORT=8080 -e APP_ENV=prod \
    -e OPENAI_API_KEY=sk-fake-0000 -e TAVILY_API_KEY=tvly-fake-0000 \
    -p 8084:8080 agent-api:0.4.0
$ docker logs b4run       # three of its lines
 🌐 Server started at http://0.0.0.0:8080
16:34:09 INFO research_assistant.api request_id=- user_id=- session_id=- | agent ready in 67 ms: model=openai:gpt-6-luna prompt_sha256=439f527b5660 checkpointer=memory
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
$ docker ps --format "{{.Names}}  {{.Status}}"
b4run  Up 40 seconds (healthy)
$ curl -s localhost:8084/health
{"status":"ok"}
$ curl -s localhost:8084/ready
{"status":"ready","checks":{"agent":"ok","sessions":"ok","accepting":"ok"}}
$ curl -s localhost:8084/v1/info -H "Authorization: Bearer alice-dev-token"
{"service":"research-assistant","version":"0.4.0","app_env":"prod","model":"openai:gpt-6-luna","prompt_sha256":"439f527b5660","revision":null}
```
`(healthy)`: the `HEALTHCHECK` now calls port 8080. With the Session 03 Dockerfile (`127.0.0.1:8000`) Docker reports
`starting` and then `unhealthy`. `revision` is `null` because `K_REVISION` only exists on Cloud Run.

**A fake key starts the service, but a run fails.** Same container:
```
$ curl -N -X POST $API/v1/sessions/$SID/runs -H "$ALICE" \
    -H "Content-Type: application/json" -d @payloads/run_ok.json
event: metadata
data: {"run_id": "4d3c218c", "session_id": "3479e654-34e6-4330-85f1-12bca695b6ed"}

event: error
data: {"type": "about:blank", "title": "Bad Gateway", "status": 502, "detail": "The model provider failed to answer.", "instance": "/v1/sessions/3479e654-34e6-4330-85f1-12bca695b6ed/runs", "request_id": "9f53fddeb7b4"}
```
The log line with the same `request_id`:
```
16:34:55 ERROR research_assistant.api.routers.runs request_id=9f53fddeb7b4 user_id=alice session_id=3479e654-34e6-4330-85f1-12bca695b6ed | run 4d3c218c failed: 502 OpenAIAuthenticationError('Error code: 401 - Incorrect API key provided: sk-fake-0000. …')
```

**Keys passed as environment variables are readable from the container configuration:**
```
$ docker inspect b4run --format '{{json .Config.Env}}'
["OPENAI_API_KEY=sk-fake-0000","TAVILY_API_KEY=tvly-fake-0000","PORT=8080","APP_ENV=prod","PATH=…", …]
```
Cloud Run has the same problem with `--set-env-vars` (Challenge 3). Stop the container: `docker rm -f b4run`.

**No key in the image, but the demo token file is.**
```
$ docker history --no-trunc agent-api:0.4.0 | grep -c -E "sk-|API_KEY"
0
$ docker run --rm --entrypoint cat agent-api:0.4.0 /app/data/users.json
{ … "tokens": { "alice-dev-token": "alice", "bob-dev-token": "bob" } }
```
Anyone who reads this repository knows `alice-dev-token`. On a public URL that token would let anyone run the agent
with **your** OpenAI key. Challenge 4 replaces the file with one from Secret Manager.

## Lab (≈ 60 min core + extension at home)

| Time | Part |
|---|---|
| 0–6 | 1. **Challenge 1**: project, APIs, budget; start creating Cloud SQL (`--async`) |
| 6–12 | 2. **Challenge 2**: Artifact Registry, push, digest |
| 12–22 | 3. **Challenge 3**: first deploy, public URL, read the configuration |
| 22–34 | 4. **Challenge 4**: service account, Secret Manager, a new token file |
| 34–46 | 5. **Challenge 5**: Cloud SQL as the checkpointer |
| 46–54 | 6. **Challenge 6**: a bad revision, logs, rollback |
| 54–60 | 7. **Challenge 7**: cost and cleanup |

After **every** deploy, check that the old demo token no longer works once Challenge 4 is done:
`curl -s -o /dev/null -w "%{http_code}\n" $URL/v1/info -H "Authorization: Bearer alice-dev-token"` → `401`.

### 1. Challenge 1 — project, APIs, budget, Cloud SQL (6 min)

```bash
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud config set run/region us-central1
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com
gcloud services list --enabled \
  --filter="name~(run|artifactregistry|secretmanager|sqladmin)"
```
Check the budget in Console → Billing → Budgets & alerts (thresholds 50 %, 90 %, 100 % by default).

Creating a Cloud SQL instance takes minutes, so start it now and use it in Challenge 5:
```bash
gcloud sql instances create \
 agent-pg \
 --database-version=POSTGRES_18 \
 --edition=ENTERPRISE \
 --tier=db-f1-micro \
 --region=us-central1 --async
```
- PostgreSQL 16 and later default to the Enterprise Plus edition.
- The shared-core tier `db-f1-micro` only exists in the Enterprise edition.
- `db-f1-micro` has no SLA and costs about $0.0105 per hour in us-central1. It is billed while it exists, so you
  delete it **first** in Challenge 7.

### 2. Challenge 2 — Artifact Registry and the digest (6 min)

```bash
gcloud artifacts repositories \
  create agentops \
  --repository-format=docker \
  --location=us-central1
gcloud auth configure-docker \
  us-central1-docker.pkg.dev
docker tag agent-api:0.4.0 $IMAGE
docker push $IMAGE
IMAGE_DIGEST=$(docker inspect \
 --format='{{index .RepoDigests 0}}' \
 $IMAGE)
echo $IMAGE_DIGEST
```
Check:
- the last line of `docker push` prints `0.4.0: digest: sha256:…`;
- Console → Artifact Registry → `agentops` → `agent-api` shows tag `0.4.0` with the same digest;
- `IMAGE_DIGEST` is `us-central1-docker.pkg.dev/…/agent-api@sha256:…`.

A tag can be moved to another image; a digest cannot. Every deploy below uses `$IMAGE_DIGEST`.

### 3. Challenge 3 — first deploy and the public URL (10 min)

The first deploy declares the whole configuration of the revision. The keys are **fake** on purpose: the app refuses
to start without keys, and this step shows why keys do not belong in `--set-env-vars`.
```bash
gcloud run deploy agent-api \
 --image=$IMAGE_DIGEST \
 --region=us-central1 --max=1 \
 --set-env-vars=APP_ENV=prod,\
CHECKPOINTER=memory,\
OPENAI_API_KEY=sk-fake-0000,\
TAVILY_API_KEY=tvly-fake-0000 \
 --startup-probe=httpGet.path=/ready,\
timeoutSeconds=3 \
 --liveness-probe=\
httpGet.path=/health \
 --no-invoker-iam-check
```
- `--max=1`: with the in-memory checkpointer, two instances would not see each other's sessions.
- `--startup-probe`: `/ready` checks the agent and (later) the database. `timeoutSeconds=3` because `/ready` waits up
  to 2 s for the database and the HTTP probe default is 1 s.
- `--liveness-probe`: `/health` calls no dependency, so a slow database does not restart every instance.
- `--no-invoker-iam-check`: anyone with the URL can call the service (the app still asks for its bearer token).
- `--set-env-vars` replaces **all** existing variables. Use it only for this first deploy; later deploys use
  `--update-env-vars`, `--remove-env-vars` and `--update-secrets`.

Then:
```bash
URL=$(gcloud run services describe agent-api --format='value(status.url)')
ALICE="Authorization: Bearer alice-dev-token"
curl -s $URL/health; echo; curl -s $URL/ready; echo; curl -s $URL/v1/info -H "$ALICE"; echo
echo $URL/docs       # open it in a browser
```
Check:
- `/health` and `/ready` answer over HTTPS;
- `/v1/info` shows `"revision":"agent-api-00001-…"`;
- in Console → Cloud Run → `agent-api` → Logs, the line `Uvicorn running on http://0.0.0.0:8080`.

Run the agent once (it fails with the fake key, exactly as in the local check above):
```bash
SID=$(curl -s -X POST $URL/v1/sessions -H "$ALICE" | uv run python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST $URL/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
```
Read the configuration of the revision:
```bash
gcloud run services describe agent-api --format="yaml(spec.template)"
gcloud run services describe agent-api --format="yaml(spec.template.spec.containers[0].env)"
```
In the first output, find the concurrency, the timeout, the CPU throttling and startup CPU boost annotations, and the
two probes. The second output shows `OPENAI_API_KEY` with its value. **Anyone who can view the service can read it**,
and every old revision keeps a copy.

### 4. Challenge 4 — service account, Secret Manager, a new token file (12 min)

Load your real keys into the shell from your Session 03 `.env` (the values never appear in a command):
```bash
set -a && source ../03_docker/.env && set +a     # or the .env of your own repository
```
Create the four secrets. `printf %s` adds no newline, and the key does not go into the shell history:
```bash
printf %s "$OPENAI_API_KEY" | \
 gcloud secrets create \
 openai-api-key --data-file=-
printf %s "$TAVILY_API_KEY" | gcloud secrets create tavily-api-key --data-file=-
openssl rand -hex 24 | tr -d '\n' | gcloud secrets create db-password --data-file=-
mkdir -p secrets
ALICE_TOKEN=$(openssl rand -hex 24); BOB_TOKEN=$(openssl rand -hex 24)
printf '{"tokens": {"%s": "alice", "%s": "bob"}}\n' "$ALICE_TOKEN" "$BOB_TOKEN" > secrets/users.json
gcloud secrets create agent-users --data-file=secrets/users.json
```
(`data/users.example.json` shows the shape of the file.)

Create the service account. Do **not** grant it anything yet:
```bash
gcloud iam service-accounts create agent-api-runtime --display-name="Agent API runtime"
```

**Break it first: a service account without access to the secrets.** Deploy with the command below (the same command
as the fix), before granting the roles:
```bash
gcloud run deploy agent-api \
 --image=$IMAGE_DIGEST \
 --service-account=$SA_EMAIL \
 --remove-env-vars=OPENAI_API_KEY,\
TAVILY_API_KEY \
 --update-secrets=OPENAI_API_KEY=\
openai-api-key:1,TAVILY_API_KEY=\
tavily-api-key:1,/secrets/users/\
users.json=agent-users:latest \
 --update-env-vars=USERS_FILE=\
/secrets/users/users.json
```
Expected: the deploy fails, because the service account cannot read the secrets (an environment variable secret is
resolved when the instance starts). Read the error in the output and in Logs; traffic stays on revision 1.

**Fix it:** grant `secretAccessor` on each of the four secrets (not on the whole project) and `cloudsql.client` for
Challenge 5:
```bash
for s in openai-api-key tavily-api-key db-password agent-users; do
  gcloud secrets add-iam-policy-binding $s \
    --member=serviceAccount:$SA_EMAIL --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL --role=roles/cloudsql.client
```
Run the same `gcloud run deploy` again. A new IAM binding can take a few minutes to apply; if the deploy fails with the
same error, wait and retry.

How the command works:
- `--remove-env-vars` drops the two fake literal variables, and `--update-secrets` sets the same names from Secret
  Manager. gcloud 592 applies variable changes before secret changes. If your gcloud refuses the combination, run two
  commands: `gcloud run services update agent-api --remove-env-vars=…`, then the deploy with `--update-secrets`.
- `OPENAI_API_KEY=openai-api-key:1`: an environment variable, read once when the instance starts. It is pinned to
  version 1; a new key means `--update-secrets=…:2` and a new revision.
- `/secrets/users/users.json=agent-users:latest`: a file mounted from the secret, read when the code opens the file.
  This app reads the token file once per instance (`lru_cache` in `api/deps.py`), so a new version reaches new
  instances.
- `USERS_FILE` points the app at the mounted file instead of `data/users.json` in the image.

Check:
```bash
gcloud secrets versions list openai-api-key
gcloud run services describe agent-api \
  --format="yaml(spec.template.spec.containers[0].env)"
gcloud run services describe agent-api \
  --format="yaml(spec.template.spec.volumes)"
curl -s -o /dev/null -w "%{http_code}\n" $URL/v1/info -H "Authorization: Bearer alice-dev-token"   # 401
ALICE="Authorization: Bearer $ALICE_TOKEN"
SID=$(curl -s -X POST $URL/v1/sessions -H "$ALICE" | uv run python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST $URL/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
docker history --no-trunc $IMAGE | grep -c -E "sk-|API_KEY"     # 0
```
- `env` shows `valueFrom.secretKeyRef` for the two keys, not their values.
- The run streams to `event: done`.
- Console → Security → Secret Manager → `openai-api-key` → Versions shows version 1, not its value.

The same token-file mechanism, recorded locally with a bind mount instead of Secret Manager:
```
$ docker run … -e USERS_FILE=/secrets/users/users.json \
    -v "$PWD/secrets/users.json:/secrets/users/users.json:ro" … agent-api:0.4.0
$ curl -s -o /dev/null -w "%{http_code}\n" $API/v1/info -H "Authorization: Bearer alice-dev-token"
401
$ curl -s -o /dev/null -w "%{http_code}\n" $API/v1/info -H "Authorization: Bearer $ALICE_TOKEN"
200
```

### 5. Challenge 5 — Cloud SQL as the checkpointer (12 min)

```bash
gcloud sql instances describe agent-pg --format='value(state)'     # RUNNABLE when ready
gcloud sql databases create agent --instance=agent-pg
gcloud sql users create agent --instance=agent-pg \
  --password="$(gcloud secrets versions access 1 --secret=db-password)"
gcloud run deploy agent-api \
 --image=$IMAGE_DIGEST \
 --add-cloudsql-instances=$SQL_CONN \
 --update-secrets=POSTGRES_PASSWORD=db-password:1 \
 --update-env-vars=CHECKPOINTER=postgres,DB_HOST=/cloudsql/$SQL_CONN \
 --max=2
```
- `--add-cloudsql-instances` makes Cloud Run create a Unix socket in `/cloudsql/PROJECT:us-central1:agent-pg/`.
- libpq treats a `host` that starts with `/` as a socket directory, so only `DB_HOST` changes; the code does not.
- `--max=2`: both instances now share the sessions through the database.

Check:
```bash
curl -s $URL/ready      # … "database":"ok"
SID=$(curl -s -X POST $URL/v1/sessions -H "$ALICE" | uv run python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -N -X POST $URL/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
curl -s $URL/v1/info -H "$ALICE"; echo
gcloud run services update agent-api --update-env-vars=LOG_LEVEL=DEBUG      # a new revision
curl -s $URL/v1/info -H "$ALICE"; echo                                      # the new revision
curl -s $URL/v1/sessions/$SID -H "$ALICE"; echo                             # the same messages
```

The same steps were recorded locally: Postgres shares its socket directory through a volume mounted at a
Cloud-Run-style path, and the container is replaced as a new revision would replace it.
```
$ docker run … -e CHECKPOINTER=postgres -e DB_HOST=/cloudsql/demo-project:us-central1:agent-pg \
    --mount type=volume,src=b4sock,dst=/cloudsql/demo-project:us-central1:agent-pg … agent-api:0.4.0
… agent ready in 89 ms: model=openai:gpt-6-luna prompt_sha256=439f527b5660 checkpointer=postgres
$ docker exec b4app1 ls /cloudsql/demo-project:us-central1:agent-pg
.s.PGSQL.5432  .s.PGSQL.5432.lock
$ curl -s $API/ready
{"status":"ready","checks":{"agent":"ok","sessions":"ok","accepting":"ok","database":"ok"}}

# postgres checkpointer: replace the container, read the session again
$ curl -s $API/v1/sessions/$SID -H "$ALICE"
{"session_id":"d372a27c-…","title":"What is 12000 / 2.5?",…,"messages":[{"role":"user","content":"What is 12000 / 2.5?"}]}
# memory checkpointer: the same steps
… before: 200
… after:  {"type":"about:blank","title":"Not Found","status":404,"detail":"Session 65796796-… not found",…}
```
(Docker's `-v src:dst` syntax rejects a path with `:`; `--mount` accepts it. On Cloud Run the socket is created for you.)

**Break it: `localhost`.**
```bash
gcloud run services update agent-api --update-env-vars=DB_HOST=localhost
```
Expected: the new revision fails its startup probe and traffic stays on the previous revision. Recorded locally with
the same setting:
```
WARNING psycopg.pool … error connecting in 'pool-1': connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
psycopg_pool.PoolTimeout: pool initialization incomplete after 10 sec
ERROR:    Application startup failed. Exiting.
```
**Put the value back.** The failed revision is still the service's template, so the next deploy would copy
`localhost`:
```bash
gcloud run services update agent-api --update-env-vars=DB_HOST=/cloudsql/$SQL_CONN
```

### 6. Challenge 6 — a bad revision, logs and rollback (8 min)

```bash
gcloud run services update agent-api --update-env-vars=MODEL=openai:gpt-6-lunax
curl -s $URL/health; echo                       # 200: the model is only called during a run
curl -s -D - -N -X POST $URL/v1/sessions/$SID/runs -H "$ALICE" -H "Content-Type: application/json" -d @payloads/run_ok.json
```
Copy the `x-request-id` response header. Read the logs:
- terminal: `gcloud run services logs read agent-api --limit=20`;
- Console → Logging → Logs Explorer, two queries:
  ```
  # container log: what the app wrote to stdout
  resource.type="cloud_run_revision"
  resource.labels.service_name="agent-api"
  textPayload:"<request_id>"

  # request log: what Cloud Run recorded per request
  logName:"requests"
  resource.labels.revision_name="<bad revision>"
  ```
  Lines of one query are joined with AND.
  The first finds the app's own log lines (stdout) of that request. The second finds Cloud Run's request log of the
  revision (method, status, latency); it does not contain the app's `request_id` (joining them by trace is Session 06).

Roll back by moving traffic; nothing is rebuilt or pushed:
```bash
gcloud run revisions list \
  --service=agent-api
gcloud run services update-traffic \
  agent-api \
  --to-revisions=<REV>=100
curl -s $URL/v1/info -H "$ALICE"
```
`<REV>` is the revision before the bad one; `/v1/info` now shows it.
Fix the model and send traffic to the latest revision again. Until `--to-latest`, every new deploy keeps the split you
set, so a fixed revision would get 0 %:
```bash
gcloud run services update \
  agent-api --update-env-vars=\
MODEL=openai:gpt-6-luna
gcloud run services update-traffic \
  agent-api --to-latest
```

### 7. Challenge 7 — cost and cleanup (6 min)

Console → Billing → Reports, filter on your project and group by service. Charges can take a day to appear.

Delete everything in the order of `docs/cleanup.md` (Cloud SQL first: it is the only resource that costs money while
idle), then check that both lists are empty:
```bash
gcloud sql instances list
gcloud run services list
```

### Extension (at home, ≈ 15 min)

- **Cold start.** `gcloud run deploy` starts one instance and waits for its startup probe before it reports success
  (`--deploy-health-check`, on by default), so the first request after a deploy may reach a warm instance. Leave the
  service idle (about 15 minutes), then:
  ```bash
  for i in 1 2 3; do
    curl -o /dev/null -s \
    -w "%{http_code} %{time_total}s\n" \
    $URL/health
  done
  ```
  Compare with one instance kept warm (an idle minimum instance is billed), then go back to 0:
  ```bash
  gcloud run services update \
    agent-api --min=1
  gcloud run services update \
    agent-api --min=0
  ```
- **Canary.** `gcloud run deploy agent-api --image=$IMAGE_DIGEST --no-traffic --tag canary`, call
  `https://canary---…run.app/v1/info`, then `update-traffic --to-latest`.
- **No startup probe.** Deploy a revision without `--startup-probe`: Cloud Run falls back to a TCP probe on the port.
  Uvicorn opens the port only after the lifespan start-up, so you may see no difference; write down what you see.
- **Wrong platform.** On Apple Silicon, build without `--platform linux/amd64`, push it under another tag and deploy
  it; read the error.
- **A private service.** `gcloud run services update agent-api --invoker-iam-check`, then
  `curl $URL/v1/info -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token)" -H "$ALICE"`.
  Cloud Run checks `X-Serverless-Authorization`; the app still reads its own token from `Authorization`.

## Tests

```
$ uv run pytest -q
.........................                                                [100%]
25 passed
```
New in this session: `/v1/info` has `revision` (`None` outside Cloud Run), the `HEALTHCHECK` follows `PORT`, and the
deploy files hold no secret and stay out of git.

## Troubleshooting

- `Billing account … is not found` or `… billing is disabled`: link a billing account to the project.
- `API [run.googleapis.com] not enabled`: run the `gcloud services enable` command of Challenge 1 (or answer `y`
  when gcloud offers to enable an API).
- `Container failed to start. Failed to start and then listen on the port defined by the PORT environment variable`:
  the server binds 127.0.0.1 or a fixed port, or the image is not `linux/amd64`.
- `Invalid settings` / `ValidationError … openai_api_key Field required` in the logs: a key is missing; locally:
  ```
  ValidationError: 1 validation error for Settings
  openai_api_key
    Field required [type=missing, …]
  ```
- `403 Forbidden` from Cloud Run: the invoker IAM check is on and the caller has no `roles/run.invoker`.
  `401` with `application/problem+json`: Cloud Run let the request in; the app rejected the bearer token.
- `PoolTimeout … connection to server at "127.0.0.1"`: `DB_HOST` is `localhost`; on Cloud Run it is
  `/cloudsql/$SQL_CONN`.
- `/ready` 503 with `"database":"unreachable"`: missing `--add-cloudsql-instances`, missing `roles/cloudsql.client`,
  a wrong connection name, or Cloud SQL in another region.
- A variable or secret disappeared after a deploy: `--set-env-vars` / `--set-secrets` replace everything. Use the
  `--update-*` and `--remove-*` flags.
- `allUsers` cannot be added (domain restricted sharing org policy): use `--no-invoker-iam-check`.
- Permission errors right after `add-iam-policy-binding`: IAM changes can take a few minutes.

## References

- Cloud Run: what it is https://cloud.google.com/run/docs/overview/what-is-cloud-run · container contract
  https://cloud.google.com/run/docs/container-contract · deploying https://cloud.google.com/run/docs/deploying ·
  `gcloud run deploy` https://cloud.google.com/sdk/gcloud/reference/run/deploy
- Probes https://cloud.google.com/run/docs/configuring/healthchecks · concurrency
  https://cloud.google.com/run/docs/about-concurrency · min instances
  https://cloud.google.com/run/docs/configuring/min-instances · max instances
  https://cloud.google.com/run/docs/configuring/max-instances
- Secrets https://cloud.google.com/run/docs/configuring/services/secrets · service identity
  https://cloud.google.com/run/docs/securing/service-identity · public access
  https://cloud.google.com/run/docs/authenticating/public · service-to-service
  https://cloud.google.com/run/docs/authenticating/service-to-service
- Rollouts, rollbacks and traffic https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration · logging
  https://cloud.google.com/run/docs/logging · pricing https://cloud.google.com/run/pricing
- Artifact Registry https://cloud.google.com/artifact-registry/docs/docker/store-docker-container-images · Secret
  Manager https://cloud.google.com/secret-manager/docs/overview
- Cloud SQL from Cloud Run https://cloud.google.com/sql/docs/postgres/connect-run · create an instance
  https://cloud.google.com/sql/docs/postgres/create-instance · pricing https://cloud.google.com/sql/pricing
- libpq connection parameters https://www.postgresql.org/docs/current/libpq-connect.html · budgets
  https://cloud.google.com/billing/docs/how-to/budgets
