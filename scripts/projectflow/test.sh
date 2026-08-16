#!/usr/bin/env bash
# ProjectFlow contract: test (default aggregate). Thin wrapper around the
# existing, already-isolated Docker test stack -- does not duplicate the
# test framework. Fully self-contained: own compose project ("mesflow-test"),
# own Postgres (tmpfs), no host ports, self-cleans on exit.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

echo "===== MESFlow App test (delegates to scripts/test/docker-test.sh) ====="
./scripts/test/docker-test.sh
echo "TEST PASS"
