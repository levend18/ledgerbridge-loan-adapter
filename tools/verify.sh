#!/bin/sh
set -u
mkdir -p artifacts/verification
rm -f artifacts/verification/*.xml artifacts/verification/*.exit artifacts/benchmark.json
phase() {
    name=$1
    shift
    "$@"
    code=$?
    echo "$code" > "artifacts/verification/$name.exit"
    return 0
}
# Generate a report even if a phase fails; exit status is derived from all evidence.
phase lint make lint
docker compose stop beat worker
phase tests docker compose run --rm -T dev pytest tests/verification -q -m 'not live_worker and not performance' --junitxml=artifacts/verification/tests.xml
docker compose up -d worker
POLL_INTERVAL_SECONDS=5 docker compose up -d beat
phase live docker compose run --rm -T dev pytest tests/verification -q -m live_worker --junitxml=artifacts/verification/live.xml
docker compose stop beat
phase bench sh tools/bench.sh
phase performance docker compose run --rm -T dev pytest tests/verification -q -m performance --junitxml=artifacts/verification/performance.xml
docker compose stop worker
# Restore the configured polling interval after the isolated phases.
docker compose up -d worker beat
docker compose run --rm -T dev python -m tools.verification_report
