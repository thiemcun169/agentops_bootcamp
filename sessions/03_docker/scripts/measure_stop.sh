#!/usr/bin/env bash
# Time `docker stop` with the exec-form CMD, then with the same command in shell form.
# Usage: scripts/measure_stop.sh agent-api:0.3.0
set -euo pipefail
image=${1:-agent-api:0.3.0}
TIMEFORMAT="%R s"

measure() {  # $1 = label, rest = optional command override
  local label=$1; shift
  docker run -d --name stoptest --env-file .env "$image" "$@" > /dev/null
  sleep 5                                                     # let the server start
  echo "PID 1 ($label): $(docker exec stoptest cat /proc/1/cmdline | tr '\0' ' ')"
  echo -n "docker stop ($label): "; time docker stop stoptest > /dev/null
  echo "exit code ($label): $(docker inspect stoptest --format '{{.State.ExitCode}}')"
  docker rm stoptest > /dev/null
}

measure "exec form"                                             # CMD ["fastapi", "run"]
measure "shell form" /bin/sh -c "fastapi run"                   # what CMD fastapi run turns into
