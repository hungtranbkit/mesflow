#!/usr/bin/env bash
# ProjectFlow contract: smoke. Real application-readiness checks against the
# isolated local sandbox, not just "container is running".
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

BASE_URL="http://127.0.0.1:${PF_PORT}"
CURL=(curl -fsS --max-time 10)

echo "===== MESFlow App smoke test (sandbox: $BASE_URL) ====="

echo "-- container health --"
docker inspect -f 'postgres: {{.State.Health.Status}}' mesflow-projectflow-local-postgres
docker inspect -f 'app:      {{.State.Health.Status}}' mesflow-projectflow-local-app

echo "-- HTTP readiness --"
health_json="$("${CURL[@]}" "$BASE_URL/api/system/health")"
echo "health:  $health_json"
ready_json="$("${CURL[@]}" "$BASE_URL/api/system/ready")"
echo "ready:   $ready_json"
version_json="$("${CURL[@]}" "$BASE_URL/api/system/version")"
echo "version: $version_json"

python3 - "$ready_json" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
ok = d.get("ready", d.get("ok", d.get("status") in ("ok", "ready")))
if not ok:
    print(f"SMOKE FAIL: /api/system/ready did not report ready: {d}", file=sys.stderr)
    sys.exit(1)
PY

echo "-- login page reachable (browser-facing smoke, not just API) --"
"${CURL[@]}" -o /dev/null "$BASE_URL/login"

echo "SMOKE PASS"
