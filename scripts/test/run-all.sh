#!/usr/bin/env sh
set -eu

: "${MESFLOW_ENV:=test}"
: "${MESFLOW_SECRET_KEY:=mesflow-test-secret-key}"
export MESFLOW_ENV MESFLOW_SECRET_KEY

if [ "$MESFLOW_ENV" = "production" ]; then
  printf '%s\n' '[MESFlow TEST] Refusing to run tests with MESFLOW_ENV=production' >&2
  exit 2
fi
if [ -z "$MESFLOW_SECRET_KEY" ] || [ "$MESFLOW_SECRET_KEY" = "CHANGE_ME" ] || [ "$MESFLOW_SECRET_KEY" = "dev-only" ]; then
  printf '%s\n' '[MESFlow TEST] MESFLOW_SECRET_KEY is missing or unsafe' >&2
  exit 2
fi

printf '[MESFlow TEST] Environment: %s\n' "$MESFLOW_ENV"
mkdir -p test-results
printf '\n[MESFlow TEST] Unit tests\n'
pytest -q -m 'unit and not postgres' --junitxml=test-results/unit.xml
printf '\n[MESFlow TEST] Intentional static/package contracts\n'
pytest -q -m 'static and not postgres' --junitxml=test-results/static.xml
printf '\n[MESFlow TEST] Critical behavioral PostgreSQL/API tests\n'
pytest -q -m 'behavior and integration' --timeout=120 --junitxml=test-results/behavior.xml
printf '\n[MESFlow TEST] Remaining PostgreSQL/API integration tests\n'
pytest -q -m 'integration and not behavior' --timeout=240 --junitxml=test-results/integration.xml
printf '\n[MESFlow TEST] All suites passed\n'
