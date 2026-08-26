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
# Reliability Validation Round 2, FIX 1: the CURRENTLY-RUNNING app's own
# live migration_head (read from its own /api/system/ready, generated at
# runtime straight from alembic_version -- not string-parsed from any
# manifest, so it's correct regardless of how this target got to its
# current state) is the ground truth this deploy's rollback decision will
# need if health fails AFTER this deploy's migration runs. See the
# migration-aware rollback block below.
CURRENT_MIGHEAD="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('migration_head') or '')" "$CURRENT_READY" 2>/dev/null || echo '')"
if [[ "$CURRENT_ROLE" != "None" && "$CURRENT_ROLE" != "$SERVER_ROLE" ]]; then
  echo "ABORT: currently-running app reports server_role='$CURRENT_ROLE', expected '$SERVER_ROLE'. Refusing to deploy -- wrong target." >&2
  exit 1
fi
echo "current server_role: $CURRENT_ROLE (ok) | current version: $CURRENT_VERSION | current migration_head: ${CURRENT_MIGHEAD:-<none, first deploy>}"

PREVIOUS_DIGEST="$(running_digest "$APP_CONTAINER")"
echo "previous digest: ${PREVIOUS_DIGEST:-<none, first deploy>}"

echo "-- pull --"
ssh_target "$TARGET" "docker pull ${IMAGE_REF}"

echo "-- migrate (same image, target DB) --"
ssh_target "$TARGET" "set -a; . ${REMOTE_DIR}/.env; set +a; docker run --rm --network ${NETWORK} -e DATABASE_URL=\"\$DATABASE_URL\" -e MESFLOW_SECRET_KEY=migration-run-only -e MESFLOW_ADMIN_PASSWORD=migration-run-only1 -e MESFLOW_ENV=production --entrypoint sh ${IMAGE_REF} -c 'cd /app && python -m mesflow.cli wait-db && alembic upgrade head'"

echo "-- recreate app only (db/cloudflared untouched) --"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && grep -q '^MESFLOW_IMAGE=' .env && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${IMAGE_REF}#\" .env || echo 'MESFLOW_IMAGE=${IMAGE_REF}' >> .env"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"

echo "-- scheduler (host cron: exception/shift reconciliation, log retention) --"
# Codex audit: a successful deploy used to leave code+CLI present
# but the maintenance cron NEVER installed on a fresh/rebuilt target (no
# step anywhere ran install-reconcile-cron.sh / install-log-retention-cron.sh).
# Both installers already staged into ${REMOTE_DIR}/scripts by the source
# stage (scripts/install.sh); MESFLOW_APP_SERVICE must match this target's
# real compose service name (prodtest's is NOT "mesflow" -- see
# deploy_lib.sh's target_config()), which is why this is not hardcoded.
SCHEDULER_INSTALL_OK=1
ssh_target "$TARGET" "cd ${REMOTE_DIR} && MESFLOW_ROOT=${REMOTE_DIR} MESFLOW_APP_SERVICE=${APP_SERVICE} sh scripts/install-reconcile-cron.sh" || SCHEDULER_INSTALL_OK=0
ssh_target "$TARGET" "cd ${REMOTE_DIR} && MESFLOW_ROOT=${REMOTE_DIR} MESFLOW_APP_SERVICE=${APP_SERVICE} sh scripts/install-log-retention-cron.sh" || SCHEDULER_INSTALL_OK=0
SCHEDULER_OK=0
if ssh_target "$TARGET" "sh ${REMOTE_DIR}/scripts/verify-scheduler-cron.sh"; then
  SCHEDULER_OK=1
fi
echo "scheduler cron installed: ${SCHEDULER_INSTALL_OK} | verified present: ${SCHEDULER_OK}"

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
echo "scheduler cron verified: ${SCHEDULER_OK}"

PASS=1
[[ -n "$HEALTHY" ]] || PASS=0
[[ "$NEW_ROLE" == "$SERVER_ROLE" ]] || PASS=0
[[ "$DB_OK" == "True" ]] || PASS=0
[[ -n "$NEW_DIGEST" && "$NEW_DIGEST" == "$IMAGE_REF" ]] || PASS=0
# Codex audit: do not report deploy PASS when the mandatory
# reconciliation/log-retention cron jobs are absent from the target's
# crontab -- an app that's otherwise healthy but silently unscheduled is
# exactly the "code present, cron missing, scheduler never runs" bug found.
[[ "$SCHEDULER_OK" == "1" ]] || PASS=0

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# migration_changed drives the entire rollback branch below -- computed
# once, from the two live-observed revisions, never assumed.
MIGRATION_CHANGED=0
[[ -n "$CURRENT_MIGHEAD" && "$CURRENT_MIGHEAD" != "$NEW_MIGHEAD" ]] && MIGRATION_CHANGED=1
echo "migration_before: ${CURRENT_MIGHEAD:-<none>} | migration_after: ${NEW_MIGHEAD:-<none>} | migration_changed: $MIGRATION_CHANGED"

if [[ "$PASS" == "1" ]]; then
  ssh_target "$TARGET" "cat > ${REMOTE_DIR}/deploy-state.json" <<EOF
{"version":"$NEW_VERSION","commit":"$NEW_COMMIT","image":"$IMAGE_REF","digest":"$NEW_DIGEST","migration_head":"$NEW_MIGHEAD","previous_digest":"$PREVIOUS_DIGEST","previous_migration_head":"$CURRENT_MIGHEAD","server_role":"$SERVER_ROLE","deployed_at":"$TS","scheduler_cron_verified":$([[ "$SCHEDULER_OK" == "1" ]] && echo true || echo false)}
EOF
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"deploy\",\"from_digest\":\"$PREVIOUS_DIGEST\",\"to_digest\":\"$NEW_DIGEST\",\"from_migration\":\"$CURRENT_MIGHEAD\",\"to_migration\":\"$NEW_MIGHEAD\",\"migration_changed\":$([[ "$MIGRATION_CHANGED" == "1" ]] && echo true || echo false),\"result\":\"PASS\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  echo "== DEPLOY PASS =="
  exit 0
fi

echo "== DEPLOY HEALTH CHECK FAILED =="
if [[ -z "$PREVIOUS_DIGEST" ]]; then
  echo "No previous digest to roll back to (first deploy on this target). Leaving as-is for manual inspection." >&2
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"deploy\",\"from_digest\":\"$PREVIOUS_DIGEST\",\"to_digest\":\"$NEW_DIGEST\",\"result\":\"FAIL_NO_ROLLBACK_TARGET\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  exit 1
fi

# Reliability Validation Round 2, FIX 1 (Gate 12's confirmed P1 bug): an
# app-image-only rollback does not restore service once the schema has
# moved forward -- see docs/operations/ROLLBACK.md for the live-tested
# proof (old app image crash-loops with "Can't locate revision..." against
# a schema it doesn't know about). Only take the fast image-only path when
# this deploy genuinely never advanced the schema.
if [[ "$MIGRATION_CHANGED" == "0" ]]; then
  echo "-- auto-rollback to $PREVIOUS_DIGEST (image only -- this deploy did not change the migration head, so the schema is already compatible) --"
  ssh_target "$TARGET" "cd ${REMOTE_DIR} && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${PREVIOUS_DIGEST}#\" .env && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"
  ROLLBACK_STATUS="starting"
  for i in $(seq 1 30); do
    ROLLBACK_STATUS="$(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
    [[ "$ROLLBACK_STATUS" == "healthy" ]] && break
    sleep 2
  done
  if [[ "$ROLLBACK_STATUS" == "healthy" ]]; then
    ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"migration_changed\":false,\"result\":\"AUTO_ON_FAILED_DEPLOY\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
    echo "Rolled back to $PREVIOUS_DIGEST (image only, schema unchanged, health verified). Deploy of $IMAGE_REF FAILED."
  else
    # Never report a rollback as successful when the app is not actually
    # healthy -- the FAILED image itself may be broken for reasons
    # unrelated to migrations.
    ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"migration_changed\":false,\"result\":\"IMAGE_ROLLBACK_FAILED\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
    echo "ROLLBACK FAILED: image swapped to $PREVIOUS_DIGEST but health check did not pass (status: $ROLLBACK_STATUS). App remains unavailable -- manual intervention required." >&2
  fi
  exit 1
fi

echo "-- migration-aware auto-rollback: schema advanced ($CURRENT_MIGHEAD -> $NEW_MIGHEAD), downgrading before swapping the image back --"
DOWNGRADE_OK=0
if ssh_target "$TARGET" "set -a; . ${REMOTE_DIR}/.env; set +a; docker run --rm --network ${NETWORK} -e DATABASE_URL=\"\$DATABASE_URL\" -e MESFLOW_SECRET_KEY=migration-run-only -e MESFLOW_ADMIN_PASSWORD=migration-run-only1 -e MESFLOW_ENV=production --entrypoint sh ${IMAGE_REF} -c 'cd /app && alembic downgrade ${CURRENT_MIGHEAD}'"; then
  # Verify the downgrade actually landed on the expected revision --
  # never trust alembic's exit code alone as proof of the resulting state.
  # Anchor on the NNNN_name revision-id convention every migration file in
  # this repo follows (verified: app/migrations/versions/*.py has no
  # exception) rather than a bare '^[0-9a-zA-Z_]+', which could
  # accidentally match an unrelated alembic INFO log line instead of the
  # actual current-revision line.
  #
  # Gate 23 (2026-08-26): real confirmed bug, found live via a disposable
  # fixture deploy -- this call was missing the same
  # -e MESFLOW_SECRET_KEY=... -e MESFLOW_ADMIN_PASSWORD=... -e MESFLOW_ENV=
  # production its two sibling `docker run --entrypoint sh` calls above
  # (the migrate step and the downgrade step itself) both carry. Without
  # them, migrations/env.py's `from mesflow.core.config import settings`
  # import hits config.py's own production safety check (secret_key=="" is
  # refused in production) and crashes before alembic can print a revision
  # line at all -- so DOWNGRADED_HEAD came back empty, DOWNGRADE_OK never
  # became 1, and ROLLBACK_REQUIRES_HUMAN fired on every single
  # migration-changed rollback even when the downgrade immediately above
  # had ALREADY succeeded (verified live: the same downgrade command,
  # run with these env vars, exits 0 and lands exactly on
  # CURRENT_MIGHEAD). Fails toward safety (a human gets paged instead of a
  # silently wrong auto-rollback), but turns every schema-changing
  # deploy failure into a forced manual intervention instead of the
  # automatic recovery this whole mechanism exists to provide.
  DOWNGRADED_HEAD="$(ssh_target "$TARGET" "set -a; . ${REMOTE_DIR}/.env; set +a; docker run --rm --network ${NETWORK} -e DATABASE_URL=\"\$DATABASE_URL\" -e MESFLOW_SECRET_KEY=migration-run-only -e MESFLOW_ADMIN_PASSWORD=migration-run-only1 -e MESFLOW_ENV=production --entrypoint sh ${IMAGE_REF} -c 'cd /app && alembic current' 2>/dev/null" | grep -oE '^[0-9]{4}_[0-9a-zA-Z_]+' || true)"
  [[ "$DOWNGRADED_HEAD" == "$CURRENT_MIGHEAD" ]] && DOWNGRADE_OK=1
fi

if [[ "$DOWNGRADE_OK" != "1" ]]; then
  # Downgrade failure: do not continue blindly swapping images. The schema
  # is left wherever the failed/partial downgrade left it (NOT reverted to
  # a confirmed-known-good state) -- swapping to the old app image now
  # would very likely repeat the exact "Can't locate revision" crash-loop
  # this whole mechanism exists to prevent, or worse, run the old app
  # against a half-downgraded schema. Preserve the NEW (already-migrated)
  # app/schema combination -- it is not healthy, but it is at least the
  # one combination we know the actual state of -- and surface the exact
  # manual recovery command instead of guessing further.
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"from_migration\":\"$NEW_MIGHEAD\",\"to_migration\":\"$CURRENT_MIGHEAD\",\"migration_changed\":true,\"result\":\"ROLLBACK_REQUIRES_HUMAN\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  echo "== ROLLBACK_REQUIRES_HUMAN ==" >&2
  echo "Migration downgrade to $CURRENT_MIGHEAD could not be verified. The app image was NOT swapped back (doing so against an unconfirmed schema state risks a worse crash-loop). Health remains FAILED." >&2
  echo "Recovery: inspect the target's alembic state directly, then retry the downgrade by hand:" >&2
  echo "  ssh ${SSH_USER}@${SSH_HOST} 'cd ${REMOTE_DIR} && set -a; . .env; set +a; docker run --rm --network ${NETWORK} -e DATABASE_URL=\"\$DATABASE_URL\" --entrypoint sh ${IMAGE_REF} -c \"cd /app && alembic current && alembic downgrade ${CURRENT_MIGHEAD}\"'" >&2
  exit 1
fi
echo "schema downgraded and verified at $CURRENT_MIGHEAD"

echo "-- swapping app image back to $PREVIOUS_DIGEST --"
ssh_target "$TARGET" "cd ${REMOTE_DIR} && sed -i \"s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=${PREVIOUS_DIGEST}#\" .env && docker compose --env-file .env up -d --no-deps ${APP_SERVICE}"
ROLLBACK_STATUS="starting"
for i in $(seq 1 30); do
  ROLLBACK_STATUS="$(ssh_target "$TARGET" "docker inspect --format='{{.State.Health.Status}}' ${APP_CONTAINER}" 2>/dev/null || echo starting)"
  [[ "$ROLLBACK_STATUS" == "healthy" ]] && break
  sleep 2
done

if [[ "$ROLLBACK_STATUS" == "healthy" ]]; then
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"from_migration\":\"$NEW_MIGHEAD\",\"to_migration\":\"$CURRENT_MIGHEAD\",\"migration_changed\":true,\"result\":\"AUTO_ON_FAILED_DEPLOY\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  echo "Rolled back to $PREVIOUS_DIGEST with schema downgraded to $CURRENT_MIGHEAD (health verified). Deploy of $IMAGE_REF FAILED."
else
  # The schema was correctly downgraded, but the OLD image itself failed
  # to come up healthy for some other reason -- still a failure, still
  # reported as one, never disguised as a pass.
  ssh_target "$TARGET" "echo '{\"ts\":\"$TS\",\"action\":\"rollback\",\"from_digest\":\"$NEW_DIGEST\",\"to_digest\":\"$PREVIOUS_DIGEST\",\"from_migration\":\"$NEW_MIGHEAD\",\"to_migration\":\"$CURRENT_MIGHEAD\",\"migration_changed\":true,\"result\":\"IMAGE_ROLLBACK_FAILED\"}' >> ${REMOTE_DIR}/deploy-history.jsonl"
  echo "ROLLBACK INCOMPLETE: schema downgraded to $CURRENT_MIGHEAD but the old app image did not become healthy (status: $ROLLBACK_STATUS). App remains unavailable -- manual intervention required." >&2
fi
exit 1
