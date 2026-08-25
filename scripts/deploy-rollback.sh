#!/usr/bin/env bash
# ./scripts/deploy-rollback.sh <prodtest|production>
#
# Manual rollback to the digest recorded as "previous" in the last deploy
# event. App container only -- DB schema is never auto-reverted (alembic
# downgrade is not run). Only safe when the previous image is compatible
# with the CURRENT (possibly newer) DB schema -- verify before running
# this if the last deploy's migration was non-additive.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

TARGET="${1:?usage: deploy-rollback.sh <prodtest|production>}"
target_config "$TARGET"

LAST_DEPLOY="$(ssh_target "$TARGET" "grep '\"action\":\"deploy\"' ${REMOTE_DIR}/deploy-history.jsonl 2>/dev/null | tail -1" || true)"
if [[ -z "$LAST_DEPLOY" ]]; then
  echo "No deploy history found on $TARGET -- nothing to roll back." >&2
  exit 1
fi
PREVIOUS_DIGEST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['from_digest'])" "$LAST_DEPLOY")"
if [[ -z "$PREVIOUS_DIGEST" || "$PREVIOUS_DIGEST" == "None" ]]; then
  echo "Last recorded deploy has no previous digest (was the first deploy on this target) -- nothing to roll back to." >&2
  exit 1
fi

echo "Rolling back $TARGET to $PREVIOUS_DIGEST"
if [[ "${ROLLBACK_YES:-}" == "1" ]]; then
  echo "ROLLBACK_YES=1 set -- skipping interactive confirmation."
else
  read -r -p "This does NOT revert the DB schema. Confirm previous image is DB-compatible with the current schema. Continue? [y/N] " CONFIRM
  [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]] || { echo "aborted"; exit 1; }
fi

ssh_target "$TARGET" "cd ${REMOTE_DIR} && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${PREVIOUS_DIGEST}#\" .env && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"

for i in $(seq 1 30); do
  STATUS="$(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
  [[ "$STATUS" == "healthy" ]] && break
  sleep 2
done
echo "container health: $STATUS"
ssh_target "$TARGET" "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo "health endpoint not responding"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"result\":\"MANUAL\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
[[ "$STATUS" == "healthy" ]] && exit 0 || exit 1
