#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
mkdir -p test-results
cleanup(){ docker compose -f compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cleanup
docker compose -f compose.test.yml up --build -d postgres-test mesflow-test-api
# --build here too: `run` alone reuses whatever image is already tagged for
# the service with no staleness check at all (found by real evidence: a
# 3-day-old `mesflow-test-tests` image was silently reused, producing test
# results for a stale VERSION.txt instead of current source).
docker compose -f compose.test.yml run --build --rm tests
docker compose -f compose.test.yml run --build --rm playwright
printf '\n[MESFlow TEST] Python/PostgreSQL and Playwright suites passed\n'
