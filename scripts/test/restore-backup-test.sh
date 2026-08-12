#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
mkdir -p test-results
cleanup() {
  docker compose -f compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
cleanup
docker compose -f compose.test.yml up -d --build postgres-test mesflow-test-api
docker compose -f compose.test.yml run --rm tests \
  pytest -q tests/integration/test_backup_restore.py -m postgres --timeout=240 \
  --junitxml=test-results/backup-restore.xml
