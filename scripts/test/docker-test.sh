#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
mkdir -p test-results
cleanup(){ docker compose -f compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cleanup
# Issue #25 (2026-09-07): compose.yml's default image tag drifted from
# VERSION.txt/release.json for an extended period, silently failing 24
# release-contract tests only after several minutes of Docker build/boot.
# Fail fast, with a specific message, before spending any of that time.
./scripts/check-version-sync.sh
# runtime/tutorials/ (bind-mounted read-only into mesflow-test-api below)
# is gitignored -- a fresh checkout, and every CI run, never has the real
# device-captured ESP Kiosk tutorial videos. Generate a deterministic,
# fully synthetic fixture (real, browser-playable MP4s) so
# tests/e2e/mesflow.spec.js's ESP Kiosk tutorial test is never dependent
# on runtime files that only happen to exist on one developer's machine.
./scripts/test/generate-esp-tutorial-fixture.sh
# Preflight, not a hope: fail loudly here (before spending time on
# postgres/app/tests build+boot) if the fixture the generator was
# supposed to produce is still missing/invalid for any reason -- never
# let a downstream Playwright assertion (deep inside "ESP Kiosk tutorial
# loads seven runtime videos and plays") be the first sign of an
# ENV/DATA problem.
node scripts/validate-esp-tutorial-fixture.js
docker compose -f compose.test.yml up --build -d postgres-test mesflow-test-api
# --build here too: `run` alone reuses whatever image is already tagged for
# the service with no staleness check at all (found by real evidence: a
# 3-day-old `mesflow-test-tests` image was silently reused, producing test
# results for a stale VERSION.txt instead of current source).
docker compose -f compose.test.yml run --build --rm tests
docker compose -f compose.test.yml run --build --rm playwright
printf '\n[MESFlow TEST] Python/PostgreSQL and Playwright suites passed\n'
