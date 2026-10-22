#!/bin/sh
set -eu
mkdir -p artifacts
docker compose stop beat
docker compose up -d worker
worker_id=$(docker compose ps -q worker)
: > artifacts/docker-stats.jsonl
(
  while :; do
    docker stats --no-stream --format '{"sampled_at":'"$(date +%s)"',"stats":{{json .}}}' "$worker_id" >> artifacts/docker-stats.jsonl || exit
  done
) &
stats_pid=$!
trap 'kill "$stats_pid" 2>/dev/null || true' EXIT HUP INT TERM
status=0
docker compose run --rm -T dev python -m tools.bench || status=$?
kill "$stats_pid" 2>/dev/null || true
wait "$stats_pid" 2>/dev/null || true
# Read after the host writer closes the file (Docker Desktop bind-mount coherence).
docker compose run --rm -T dev python -m tools.bench --finalize-stats || status=1
exit "$status"
