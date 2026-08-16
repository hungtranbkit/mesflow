#!/usr/bin/env bash
# ProjectFlow contract: local_deploy. Deploys the artifact scripts/projectflow/build.sh
# just built into the isolated sandbox defined by compose.projectflow-local.yml.
# Never builds (`docker compose ... up` against a file with no `build:` block
# for the app service -- see that file's header comment). Idempotent: running
# this twice reconciles to the same running state, no duplicate containers.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

if [[ -z "${MESFLOW_IMAGE:-}" ]]; then
  if [[ -f "$PF_LATEST_META" ]]; then
    MESFLOW_IMAGE="$(python3 -c "import json;print(json.load(open('$PF_LATEST_META')).get('artifact',''))")"
  fi
fi
if [[ -z "${MESFLOW_IMAGE:-}" ]]; then
  version="$(pf_version)"
  MESFLOW_IMAGE="mesflow-app:$version"
fi
export MESFLOW_IMAGE

docker image inspect "$MESFLOW_IMAGE" >/dev/null 2>&1 || {
  echo "ERROR: image '$MESFLOW_IMAGE' not found locally. Run scripts/projectflow/build.sh first." >&2
  exit 1
}

echo "===== MESFlow App deploy-local (sandbox) ====="
echo "Compose project: $PF_PROJECT"
echo "Image:           $MESFLOW_IMAGE"
echo "Port:            127.0.0.1:${PF_PORT}"

mkdir -p "$PF_ROOT/runtime-projectflow-local"/{postgres,uploads,backups,firmware}

pf_compose up -d --no-build

echo "Waiting for containers to report healthy..."
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
  app_status="$(docker inspect -f '{{.State.Health.Status}}' mesflow-projectflow-local-app 2>/dev/null || echo starting)"
  pg_status="$(docker inspect -f '{{.State.Health.Status}}' mesflow-projectflow-local-postgres 2>/dev/null || echo starting)"
  if [[ "$app_status" == "healthy" && "$pg_status" == "healthy" ]]; then
    echo "DEPLOY LOCAL PASS (app=$app_status postgres=$pg_status)"
    exit 0
  fi
  sleep 3
done

echo "DEPLOY LOCAL FAIL: containers did not become healthy within 180s (app=$app_status postgres=$pg_status)" >&2
pf_compose ps
exit 1
