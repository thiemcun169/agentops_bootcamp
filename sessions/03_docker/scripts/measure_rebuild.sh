#!/usr/bin/env bash
# Time a rebuild after a one-line code change.  Usage: scripts/measure_rebuild.sh Dockerfile agent-api:0.3.0
set -euo pipefail
dockerfile=${1:-Dockerfile}; tag=${2:-agent-api:0.3.0}
file=src/research_assistant/agent/agent.py
TIMEFORMAT="%R s"

docker build -q -f "$dockerfile" -t "$tag" . > /dev/null      # warm the cache first
cp "$file" "$file.bak"; trap 'mv "$file.bak" "$file"' EXIT
echo "# rebuild probe $(date +%s)" >> "$file"                  # the one-line change
echo "rebuild of $tag ($dockerfile) after a one-line change:"
time docker build -q -f "$dockerfile" -t "$tag" . > /dev/null
docker image ls "$tag"
