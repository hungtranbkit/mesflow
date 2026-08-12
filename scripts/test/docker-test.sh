#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
mkdir -p test-results
cleanup(){ docker compose -f compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cleanup
docker compose -f compose.test.yml up --build -d postgres-test mesflow-test-api
docker compose -f compose.test.yml run --rm tests
docker compose -f compose.test.yml run --rm playwright
printf '\n[MESFlow TEST] Python/PostgreSQL and Playwright suites passed\n'
