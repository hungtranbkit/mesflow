#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
docker compose -f compose.test.yml ps
docker compose -f compose.test.yml logs --tail=120 mesflow-test-api tests
