#!/usr/bin/env bash
# ProjectFlow contract: local_status. Concise, parseable KEY=VALUE output
# for the isolated sandbox only (never the shared/real deployment).
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

app_running="$(docker inspect -f '{{.State.Running}}' mesflow-projectflow-local-app 2>/dev/null || echo false)"
app_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' mesflow-projectflow-local-app 2>/dev/null || echo absent)"
pg_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' mesflow-projectflow-local-postgres 2>/dev/null || echo absent)"

version=""
if [[ "$app_running" == "true" ]]; then
  version="$(curl -fsS --max-time 5 "http://127.0.0.1:${PF_PORT}/api/system/version" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin).get('version',''))" 2>/dev/null || true)"
fi
[[ -z "$version" ]] && version="$(pf_version)"

overall="down"
[[ "$app_running" == "true" && "$app_health" == "healthy" && "$pg_health" == "healthy" ]] && overall="healthy"
[[ "$app_running" == "true" && "$app_health" != "healthy" ]] && overall="starting"

echo "SERVICE=mesflow-app"
echo "ENV=local-sandbox"
echo "COMPOSE_PROJECT=$PF_PROJECT"
echo "STATUS=$overall"
echo "VERSION=$version"
echo "APP_CONTAINER=mesflow-projectflow-local-app"
echo "APP_RUNNING=$app_running"
echo "APP_HEALTH=$app_health"
echo "POSTGRES_HEALTH=$pg_health"
echo "URL=http://127.0.0.1:${PF_PORT}"
