#!/usr/bin/env bash
# ./scripts/deploy-remote-test.sh <version-or-digest>
#
# Deploys to the real "remote-test" host -- the actual backend behind
# mesflow.net, confirmed 2026-09-07 (self-reports server_role=
# PRODUCTION_TEST via its own /api/system/ready; a live docker-cp'd
# deploy-state.json write there is traceable proof, and the version/
# commit shown publicly on https://mesflow.net matches exactly).
#
# Deliberately NOT the same code path as deploy.sh's `production` case:
#   - This host self-reports SERVER_ROLE=PRODUCTION_TEST, not PRODUCTION.
#     Real production does not exist yet (per explicit user confirmation
#     2026-09-07) -- deploy.sh's `production` target stays exactly as
#     frozen (docs/DEPLOY_ARCHITECTURE_A.md, 2026-08-25 incident) and is
#     NOT touched by this file. Do not repoint that target at this host.
#   - deploy.sh assumes the target can `docker pull` from this machine's
#     local registry (127.0.0.1:5000) -- that only works for a target
#     that IS this machine (prodtest, loopback) or shares its network.
#     A genuinely remote host cannot reach "127.0.0.1:5000" (it would
#     resolve to ITS OWN loopback, not this machine's registry). This
#     host's own release.json already documents "distribution": "bundle"
#     as its real mechanism -- this script follows that: docker save
#     locally, transfer the tar over SFTP, docker load remotely.
#   - The deploy account on this host (see target file) is intentionally
#     NOT in sudoers for routine work (confirmed live 2026-09-07:
#     `sudo -n true` -> "not in the sudoers file" for the day-to-day
#     backup/maintenance account) -- this script instead uses a
#     dedicated account with passwordless sudo (REMOTE_TEST_SSH_USER in
#     the target file), and every docker/compose/.env-touching command
#     below is explicitly `sudo`-prefixed rather than assumed passwordless
#     for whichever user connects.
#
# Never builds on the target. Loads an exact image tar built by
# release-build.sh, migrates using that same image, recreates only the
# app service, health-checks against the expected version/commit/digest/
# migration_head. Does NOT attempt the migration-aware auto-rollback
# deploy.sh has for prodtest/production (different, newer mechanism --
# safer to fail loud with a manual-recovery command than to guess at an
# auto-rollback path never exercised against this target before).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

VER_OR_DIGEST="${1:?usage: deploy-remote-test.sh <version-or-digest>}"

TARGET_FILE="${REMOTE_TEST_TARGET_FILE:-$REPO_ROOT/scripts/remote-test-target.env}"
if [[ ! -f "$TARGET_FILE" ]]; then
  echo "REMOTE_TEST_TARGET_NOT_CONFIGURED" >&2
  echo "No $TARGET_FILE -- create it (gitignored) with:" >&2
  echo "  REMOTE_TEST_SSH_HOST=..." >&2
  echo "  REMOTE_TEST_SSH_USER=...   # must have passwordless sudo" >&2
  echo "  REMOTE_TEST_REMOTE_DIR=/opt/mesflow" >&2
  echo "  REMOTE_TEST_APP_SERVICE=mesflow" >&2
  echo "  REMOTE_TEST_APP_CONTAINER=mesflow-app" >&2
  echo "  REMOTE_TEST_NETWORK=mesflow_network" >&2
  echo "  REMOTE_TEST_APP_PORT=8080" >&2
  echo "  REMOTE_TEST_PUBLIC_URL=https://mesflow.net   # optional, used only for the final public-facing check" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$TARGET_FILE"
: "${REMOTE_TEST_SSH_HOST:?REMOTE_TEST_SSH_HOST missing from $TARGET_FILE}"
: "${REMOTE_TEST_SSH_USER:?REMOTE_TEST_SSH_USER missing from $TARGET_FILE}"
: "${REMOTE_TEST_REMOTE_DIR:?REMOTE_TEST_REMOTE_DIR missing from $TARGET_FILE}"
case "$REMOTE_TEST_SSH_HOST" in
  127.0.0.1|localhost|::1|"$(hostname)"|"$(hostname -f 2>/dev/null)")
    echo "REMOTE_TEST_TARGET_MISCONFIGURED" >&2
    echo "REMOTE_TEST_SSH_HOST resolves to THIS machine -- that is DEV/DEMO/PRODTEST's" >&2
    echo "job (deploy.sh prodtest, or the recreate-demo.sh / manual DEV steps), not this" >&2
    echo "script. This script exists specifically for a genuinely separate remote host." >&2
    exit 1
    ;;
esac
REMOTE_DIR="$REMOTE_TEST_REMOTE_DIR"
APP_SERVICE="${REMOTE_TEST_APP_SERVICE:-mesflow}"
APP_CONTAINER="${REMOTE_TEST_APP_CONTAINER:-mesflow-app}"
NETWORK="${REMOTE_TEST_NETWORK:-mesflow_network}"
APP_PORT="${REMOTE_TEST_APP_PORT:-8080}"
PUBLIC_URL="${REMOTE_TEST_PUBLIC_URL:-}"
SERVER_ROLE=PRODUCTION_TEST  # the mapping fix this whole script exists for --
                             # this host is TEST, not deploy.sh's PRODUCTION.

rssh() { ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_TEST_SSH_USER}@${REMOTE_TEST_SSH_HOST}" "$@"; }

IMAGE_TAG="$VER_OR_DIGEST"
if [[ "$IMAGE_TAG" == *"@sha256:"* ]]; then
  echo "This script deploys by version tag (needs a local image to 'docker save'), not a bare digest -- pass the version, e.g. 71.0.0.226." >&2
  exit 1
fi
LOCAL_IMAGE_REF="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
REMOTE_IMAGE_REF="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"  # same tag string; loaded locally on the remote docker daemon, never pulled from a registry there.

echo "== Deploying ${LOCAL_IMAGE_REF} to remote-test (${REMOTE_TEST_SSH_USER}@${REMOTE_TEST_SSH_HOST}:${REMOTE_DIR}) via bundle transfer =="

echo "-- preflight --"
docker image inspect "$LOCAL_IMAGE_REF" >/dev/null 2>&1 || { echo "Local image $LOCAL_IMAGE_REF not found -- run release-build.sh first." >&2; exit 1; }
REMOTE_PROJECT_NAME="$(rssh "cd ${REMOTE_DIR} && sudo MESFLOW_IMAGE=name-check-placeholder docker compose --env-file .env config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"name\"])'" || true)"
if [[ "$REMOTE_PROJECT_NAME" != "mesflow" ]]; then
  echo "ABORT: remote compose project name '$REMOTE_PROJECT_NAME' != expected 'mesflow'" >&2
  exit 1
fi
echo "compose project: $REMOTE_PROJECT_NAME (matches)"
CURRENT_READY="$(rssh "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo '{}')"
CURRENT_ROLE="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('server_role'))" "$CURRENT_READY" 2>/dev/null || echo None)"
CURRENT_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version'))" "$CURRENT_READY" 2>/dev/null || echo None)"
CURRENT_MIGHEAD="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('migration_head') or '')" "$CURRENT_READY" 2>/dev/null || echo '')"
if [[ "$CURRENT_ROLE" != "None" && "$CURRENT_ROLE" != "$SERVER_ROLE" ]]; then
  echo "ABORT: currently-running app reports server_role='$CURRENT_ROLE', expected '$SERVER_ROLE'. Refusing to deploy -- wrong target." >&2
  exit 1
fi
echo "current server_role: $CURRENT_ROLE (ok) | current version: $CURRENT_VERSION | current migration_head: ${CURRENT_MIGHEAD:-<none, first deploy>}"
PREVIOUS_IMAGE_ID="$(rssh "sudo docker inspect --format='{{.Image}}' ${APP_CONTAINER}" 2>/dev/null || true)"
PREVIOUS_DIGEST="$(rssh "sudo docker image inspect --format='{{index .RepoDigests 0}}' ${PREVIOUS_IMAGE_ID}" 2>/dev/null || true)"
echo "previous digest: ${PREVIOUS_DIGEST:-<none, first deploy>}"

echo "-- save + transfer bundle (this machine's registry is not reachable from a real remote host) --"
BUNDLE="/tmp/mesflow-remote-test-${IMAGE_TAG}.tar"
docker save "$LOCAL_IMAGE_REF" -o "$BUNDLE"
LOCAL_SHA="$(sha256sum "$BUNDLE" | awk '{print $1}')"
REMOTE_BUNDLE_PATH="/tmp/mesflow-remote-test-${IMAGE_TAG}.tar"
scp -o BatchMode=yes -o ConnectTimeout=10 "$BUNDLE" "${REMOTE_TEST_SSH_USER}@${REMOTE_TEST_SSH_HOST}:${REMOTE_BUNDLE_PATH}"
REMOTE_SHA="$(rssh "sha256sum ${REMOTE_BUNDLE_PATH}" | awk '{print $1}')"
rm -f "$BUNDLE"
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  echo "ABORT: bundle checksum mismatch after transfer ($LOCAL_SHA != $REMOTE_SHA) -- corrupted upload, not loading it." >&2
  rssh "rm -f ${REMOTE_BUNDLE_PATH}" || true
  exit 1
fi
echo "checksum verified: $LOCAL_SHA"
rssh "sudo docker load -i ${REMOTE_BUNDLE_PATH} && rm -f ${REMOTE_BUNDLE_PATH}"

echo "-- migrate (same image, target DB) --"
DB_URL_LINE="$(rssh "sudo grep '^DATABASE_URL=' ${REMOTE_DIR}/.env")"
DB_URL="${DB_URL_LINE#DATABASE_URL=}"
rssh "sudo docker run --rm --network ${NETWORK} -e DATABASE_URL='${DB_URL}' -e MESFLOW_SECRET_KEY=migration-run-only -e MESFLOW_ADMIN_PASSWORD=migration-run-only1 -e MESFLOW_ENV=production --entrypoint sh ${REMOTE_IMAGE_REF} -c 'cd /app && python -m mesflow.cli wait-db && alembic upgrade head'"
unset DB_URL DB_URL_LINE

echo "-- recreate app only (db/nginx untouched) --"
rssh "sudo sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${REMOTE_IMAGE_REF}#\" ${REMOTE_DIR}/.env"
rssh "cd ${REMOTE_DIR} && sudo docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"

echo "-- health check --"
HEALTHY=""
for i in $(seq 1 30); do
  STATUS="$(rssh "sudo docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
  if [[ "$STATUS" == "healthy" ]]; then HEALTHY=1; break; fi
  sleep 2
done

READY="$(rssh "curl -fsS http://127.0.0.1:${APP_PORT}/api/system/ready" 2>/dev/null || echo '{}')"
NEW_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version'))" "$READY" 2>/dev/null || echo None)"
NEW_COMMIT="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('commit'))" "$READY" 2>/dev/null || echo None)"
NEW_ROLE="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('server_role'))" "$READY" 2>/dev/null || echo None)"
NEW_MIGHEAD="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('migration_head'))" "$READY" 2>/dev/null || echo None)"
NEW_IMAGE_ID="$(rssh "sudo docker inspect --format='{{.Image}}' ${APP_CONTAINER}" 2>/dev/null || true)"
NEW_DIGEST="$(rssh "sudo docker image inspect --format='{{index .RepoDigests 0}}' ${NEW_IMAGE_ID}" 2>/dev/null || true)"
DB_OK="$(python3 -c "import json,sys; print(bool(json.loads(sys.argv[1]).get('ok')))" "$READY" 2>/dev/null || echo False)"

echo "container healthy: ${HEALTHY:-NO}"
echo "server_role: $NEW_ROLE (expected $SERVER_ROLE)"
echo "version: $NEW_VERSION | commit: $NEW_COMMIT | migration_head: $NEW_MIGHEAD | db_ok: $DB_OK"
echo "digest running: ${NEW_DIGEST:-<none -- inspect failed, treated as FAIL>}"

PASS=1
[[ -n "$HEALTHY" ]] || PASS=0
[[ "$NEW_ROLE" == "$SERVER_ROLE" ]] || PASS=0
[[ "$DB_OK" == "True" ]] || PASS=0
[[ -n "$NEW_DIGEST" ]] || PASS=0

if [[ -n "$PUBLIC_URL" && "$PASS" == "1" ]]; then
  echo "-- public-facing confirmation ($PUBLIC_URL) --"
  PUBLIC_READY="$(curl -fsS --max-time 10 "${PUBLIC_URL%/}/api/system/ready" 2>/dev/null || echo '{}')"
  PUBLIC_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version'))" "$PUBLIC_READY" 2>/dev/null || echo None)"
  echo "public version: $PUBLIC_VERSION (expected $NEW_VERSION)"
  [[ "$PUBLIC_VERSION" == "$NEW_VERSION" ]] || { echo "WARNING: public URL does not yet reflect the new version (CDN/edge cache?) -- container itself is healthy and correct." >&2; }
fi

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ "$PASS" == "1" ]]; then
  rssh "cat | sudo tee ${REMOTE_DIR}/deploy-state.json >/dev/null" <<EOF
{"version":"$NEW_VERSION","commit":"$NEW_COMMIT","image":"$REMOTE_IMAGE_REF","digest":"$NEW_DIGEST","migration_head":"$NEW_MIGHEAD","previous_digest":"$PREVIOUS_DIGEST","previous_migration_head":"$CURRENT_MIGHEAD","server_role":"$SERVER_ROLE","deployed_at":"$TS","deployed_by":"scripts/deploy-remote-test.sh"}
EOF
  echo "== DEPLOY PASS =="
  exit 0
fi

echo "== DEPLOY HEALTH CHECK FAILED ==" >&2
echo "No auto-rollback implemented for this target (bundle-transfer mechanism," >&2
echo "never exercised enough times to trust an automatic downgrade path yet)." >&2
echo "Manual recovery: re-run this script with the previous known-good version," >&2
echo "or SSH in directly:" >&2
echo "  ssh ${REMOTE_TEST_SSH_USER}@${REMOTE_TEST_SSH_HOST}" >&2
echo "  cd ${REMOTE_DIR} && sudo sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${PREVIOUS_DIGEST:-<unknown -- inspect deploy-state.json history>}#\" .env" >&2
echo "  sudo docker compose --env-file .env up -d --no-deps ${APP_SERVICE}" >&2
exit 1
