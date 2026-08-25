#!/usr/bin/env bash
# ./scripts/deploy-rollback.sh <prodtest|production> [--dry-run]
#
# Manual rollback to the digest recorded as "previous" in the last deploy
# event (or, before any Architecture-A deploy has happened, the adopted
# BASELINE_ADOPTED entry -- see release-build.sh's sibling docs). App
# container only -- DB schema is never auto-reverted (alembic downgrade is
# not run). Only safe when the previous image is compatible with the
# CURRENT (possibly newer) DB schema -- verify before running this for
# real if the last deploy's migration was non-additive.
#
# --dry-run: prints what a rollback would target right now, and (if a
# newer release manifest exists locally) what it would target after that
# release is deployed. Makes zero remote changes beyond the read-only
# `cat`/`ssh` calls already needed to answer the question.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

DRY_RUN=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) TARGET="$arg" ;;
  esac
done
: "${TARGET:?usage: deploy-rollback.sh <prodtest|production> [--dry-run]}"
target_config "$TARGET"

CURRENT_STATE="$(ssh_target "$TARGET" "cat ${REMOTE_DIR}/deploy-state.json 2>/dev/null" || echo '{}')"
CURRENT_VERSION="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('version','unknown'))" "$CURRENT_STATE")"
CURRENT_DIGEST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('digest','unknown'))" "$CURRENT_STATE")"

LAST_DEPLOY="$(ssh_target "$TARGET" "grep '\"action\":\"deploy\"' ${REMOTE_DIR}/deploy-history.jsonl 2>/dev/null | tail -1" || true)"
LAST_BASELINE="$(ssh_target "$TARGET" "grep '\"action\":\"baseline\"' ${REMOTE_DIR}/deploy-history.jsonl 2>/dev/null | tail -1" || true)"

PREVIOUS_DIGEST=""
MODE=""
if [[ -n "$LAST_DEPLOY" ]]; then
  PREVIOUS_DIGEST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('from_digest') or '')" "$LAST_DEPLOY")"
  MODE="deploy"
elif [[ -n "$LAST_BASELINE" ]]; then
  PREVIOUS_DIGEST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('to_digest') or '')" "$LAST_BASELINE")"
  MODE="baseline"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "CURRENT:"
  echo "$CURRENT_VERSION  ($CURRENT_DIGEST)"
  echo
  echo "ROLLBACK TARGET:"
  if [[ "$MODE" == "deploy" && -n "$PREVIOUS_DIGEST" ]]; then
    echo "$PREVIOUS_DIGEST"
  elif [[ "$MODE" == "baseline" ]]; then
    echo "$CURRENT_VERSION baseline / no-op before first promotion (nothing has been deployed on top of the adopted baseline yet)"
  else
    echo "none recorded -- nothing to roll back to"
  fi
  LATEST_MANIFEST="$(ls -t "$RELEASE_DIR"/mesflow-*.json 2>/dev/null | head -1 || true)"
  if [[ -n "$LATEST_MANIFEST" ]]; then
    NEXT_VERSION="$(python3 -c "import json; print(json.load(open('$LATEST_MANIFEST'))['version'])")"
    if [[ "$NEXT_VERSION" != "$CURRENT_VERSION" ]]; then
      echo
      echo "After future deploy:"
      echo "$NEXT_VERSION -> rollback target $CURRENT_VERSION ($CURRENT_DIGEST)"
    fi
  fi
  echo
  echo "(dry run -- no container change)"
  exit 0
fi

if [[ -z "$PREVIOUS_DIGEST" ]]; then
  echo "No deploy/baseline history found on $TARGET -- nothing to roll back." >&2
  exit 1
fi
if [[ "$MODE" == "baseline" ]]; then
  echo "Only a BASELINE_ADOPTED entry exists (no Architecture-A deploy has happened yet on $TARGET) -- nothing to roll back FROM. Refusing." >&2
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
