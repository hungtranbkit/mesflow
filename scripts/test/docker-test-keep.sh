#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
mkdir -p test-results
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
