#!/usr/bin/env bash
# ./scripts/deploy-status.sh <prodtest|production>
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

TARGET="${1:?usage: deploy-status.sh <prodtest|production>}"
target_config "$TARGET"

echo "== $TARGET (${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}) =="
READY="$(ssh_target "$TARGET" "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo '{}')"
echo "app: $READY"
echo
echo "container health: $(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo 'not running')"
echo "running digest:    $(running_digest "$APP_CONTAINER")"
echo
echo "-- deploy-state.json --"
ssh_target "$TARGET" "cat ${REMOTE_DIR}/deploy-state.json 2>/dev/null" || echo "(none yet)"
echo
echo "-- last 5 deploy-history entries --"
ssh_target "$TARGET" "tail -5 ${REMOTE_DIR}/deploy-history.jsonl 2>/dev/null" || echo "(none yet)"

if [[ "$TARGET" == "prodtest" ]]; then
  echo
  echo "-- tunnel: cloudflared-prodtest.service --"
  systemctl --user is-active cloudflared-prodtest.service 2>&1 || true
elif [[ "$TARGET" == "production" ]]; then
  echo
  echo "-- nginx (still fronting real production) --"
  docker inspect --format='{{.State.Status}} health={{.State.Health.Status}}' mesflow-nginx 2>&1 || true
fi
