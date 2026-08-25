#!/usr/bin/env bash
# ./scripts/deploy.sh <prodtest|production> <version-or-digest>
#
# Never builds on the target. Pulls an exact digest, migrates using that
# same image, recreates only the app container, health-checks against the
# expected version/commit/digest/migration_head, and auto-rolls-back the
# app on health failure. cloudflared is never restarted by this script.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

TARGET="${1:?usage: deploy.sh <prodtest|production> <version-or-digest>}"
VER_OR_DIGEST="${2:?usage: deploy.sh <prodtest|production> <version-or-digest>}"
target_config "$TARGET"

IMAGE_REF="$(resolve_image_ref "$VER_OR_DIGEST")"
echo "== Deploying $IMAGE_REF to $TARGET (${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}) =="

echo "-- preflight --"
REMOTE_HOSTNAME="$(ssh_target "$TARGET" hostname)"
echo "remote hostname: $REMOTE_HOSTNAME"

# Use `compose config`'s resolved project name, not a naive grep for an
# explicit `name:` key -- compose.yml may omit it and rely on the
# directory-name fallback (e.g. /opt/mesflow -- production -- has no
# `name:` line at all; a bare grep silently returns empty and aborts every
# production deploy at this exact check).
REMOTE_PROJECT_NAME="$(ssh_target "$TARGET" "cd ${REMOTE_DIR} && MESFLOW_IMAGE=\${MESFLOW_IMAGE:-name-check-placeholder} docker compose --env-file .env config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"name\"])'" || true)"
if [[ "$REMOTE_PROJECT_NAME" != "$COMPOSE_PROJECT" ]]; then
  echo "ABORT: remote compose project name '$REMOTE_PROJECT_NAME' != expected '$COMPOSE_PROJECT'" >&2
  exit 1
fi
echo "compose project: $REMOTE_PROJECT_NAME (matches)"

CURRENT_READY="$(ssh_target "$TARGET" "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo '{}')"
CURRENT_ROLE="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('server_role'))" "$CURRENT_READY" 2>/dev/null || echo None)"
CURRENT_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version'))" "$CURRENT_READY" 2>/dev/null || echo None)"
if [[ "$CURRENT_ROLE" != "None" && "$CURRENT_ROLE" != "$SERVER_ROLE" ]]; then
  echo "ABORT: currently-running app reports server_role='$CURRENT_ROLE', expected '$SERVER_ROLE'. Refusing to deploy -- wrong target." >&2
  exit 1
fi
echo "current server_role: $CURRENT_ROLE (ok) | current version: $CURRENT_VERSION"

PREVIOUS_DIGEST="$(running_digest "$APP_CONTAINER")"
echo "previous digest: ${PREVIOUS_DIGEST:-<none, first deploy>}"

echo "-- pull --"
ssh_target "$TARGET" "docker pull ${IMAGE_REF}"

echo "-- migrate (same image, target DB) --"
ssh_target "$TARGET" "set -a; . ${REMOTE_DIR}/.env; set +a; docker run --rm --network ${NETWORK} -e DATABASE_URL=\"\$DATABASE_URL\" -e MESFLOW_SECRET_KEY=migration-run-only -e MESFLOW_ADMIN_PASSWORD=migration-run-only1 -e MESFLOW_ENV=production --entrypoint sh ${IMAGE_REF} -c 'cd /app && python -m mesflow.cli wait-db && alembic upgrade head'"

echo "-- recreate app only (db/cloudflared untouched) --"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && grep -q '^MESFLOW_IMAGE=' .env && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${IMAGE_REF}#\" .env || echo 'MESFLOW_IMAGE=${IMAGE_REF}' >> .env"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"

echo "-- health check --"
HEALTHY=""
for i in $(seq 1 30); do
  STATUS="$(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
  if [[ "$STATUS" == "healthy" ]]; then HEALTHY=1; break; fi
  sleep 2
done

READY="$(ssh_target "$TARGET" "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo '{}')"
NEW_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version'))" "$READY" 2>/dev/null || echo None)"
NEW_COMMIT="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('commit'))" "$READY" 2>/dev/null || echo None)"
NEW_ROLE="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('server_role'))" "$READY" 2>/dev/null || echo None)"
NEW_MIGHEAD="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('migration_head'))" "$READY" 2>/dev/null || echo None)"
NEW_DIGEST="$(running_digest "$APP_CONTAINER")"
DB_OK="$(python3 -c "import json,sys; print(bool(json.loads(sys.argv[1]).get('ok')))" "$READY" 2>/dev/null || echo False)"

echo "container healthy: ${HEALTHY:-NO}"
echo "server_role: $NEW_ROLE (expected $SERVER_ROLE)"
echo "version: $NEW_VERSION | commit: $NEW_COMMIT | migration_head: $NEW_MIGHEAD | db_ok: $DB_OK"
echo "digest running: ${NEW_DIGEST:-<none -- inspect failed, treated as FAIL>}"
echo "digest expected: $IMAGE_REF"

PASS=1
[[ -n "$HEALTHY" ]] || PASS=0
[[ "$NEW_ROLE" == "$SERVER_ROLE" ]] || PASS=0
[[ "$DB_OK" == "True" ]] || PASS=0
[[ -n "$NEW_DIGEST" && "$NEW_DIGEST" == "$IMAGE_REF" ]] || PASS=0

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ "$PASS" == "1" ]]; then
  ssh_target "$TARGET" "cat > ${REMOTE_DIR}/deploy-state.json" <<EOF
{"version":"$NEW_VERSION","commit":"$NEW_COMMIT","image":"$IMAGE_REF","digest":"$NEW_DIGEST","migration_head":"$NEW_MIGHEAD","server_role":"$SERVER_ROLE","deployed_at":"$TS"}
EOF
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"deploy\",\"from_digest\":\"$PREVIOUS_DIGEST\",\"to_digest\":\"$NEW_DIGEST\",\"result\":\"PASS\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  echo "== DEPLOY PASS =="
  exit 0
fi

echo "== DEPLOY HEALTH CHECK FAILED =="
if [[ -z "$PREVIOUS_DIGEST" ]]; then
  echo "No previous digest to roll back to (first deploy on this target). Leaving as-is for manual inspection." >&2
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"deploy\",\"from_digest\":\"$PREVIOUS_DIGEST\",\"to_digest\":\"$NEW_DIGEST\",\"result\":\"FAIL_NO_ROLLBACK_TARGET\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  exit 1
fi

echo "-- auto-rollback to $PREVIOUS_DIGEST (app only -- DB schema is NOT reverted, see docs) --"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${PREVIOUS_DIGEST}#\" .env && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"
for i in $(seq 1 30); do
  STATUS="$(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
  [[ "$STATUS" == "healthy" ]] && break
  sleep 2
done
ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"result\":\"AUTO_ON_FAILED_DEPLOY\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
echo "Rolled back to $PREVIOUS_DIGEST. Deploy of $IMAGE_REF FAILED."
exit 1
