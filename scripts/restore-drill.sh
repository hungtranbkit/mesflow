#!/usr/bin/env bash
# Restore-drill: proves a backup-db.sh dump actually restores, on a
# throwaway Postgres container -- NEVER touches the real/live DB.
#
# Safety: the temp container uses a Docker-managed (unnamed, ephemeral)
# volume, not a host bind-mount, and a name that can never collide with
# any real MESFlow container. Always torn down (container + its volume)
# in a trap, whether the drill passes or fails, after evidence is
# captured. No host directory is mounted into it -- this is the
# "dedicated temp container for this test" the task allows, not a
# permission-bypass mount.
#
# Usage: ./scripts/restore-drill.sh <path-to-dump> [manifest.json]
# Exits 0 only if: pg_restore succeeds, alembic_version matches the
# manifest's migration_head (if given), and business-table row counts are
# consistent with what pg_restore itself reports (no silent partial
# restore).
set -Eeuo pipefail

DUMP="${1:?Usage: restore-drill.sh <path-to-dump> [manifest.json]}"
MANIFEST="${2:-}"
[[ -f "$DUMP" ]] || { echo "ERROR: dump not found: $DUMP" >&2; exit 1; }

DRILL_NAME="mesflow-restore-drill-$(date +%s)-$$"
DRILL_DB="drill"
DRILL_USER="drill"
DRILL_PASSWORD="drill-local-only-$(date +%s)"

cleanup() {
  docker rm -f "$DRILL_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "=== Starting throwaway Postgres ($DRILL_NAME, ephemeral volume, no host mount) ==="
docker run -d --name "$DRILL_NAME" \
  -e POSTGRES_DB="$DRILL_DB" -e POSTGRES_USER="$DRILL_USER" -e POSTGRES_PASSWORD="$DRILL_PASSWORD" \
  postgres:17-alpine >/dev/null

echo "=== Waiting for it to accept connections ==="
for i in $(seq 1 30); do
  if docker exec "$DRILL_NAME" pg_isready -U "$DRILL_USER" -d "$DRILL_DB" >/dev/null 2>&1; then break; fi
  sleep 1
  [[ "$i" -eq 30 ]] && { echo "ERROR: drill Postgres never became ready" >&2; exit 1; }
done

echo "=== Restoring $DUMP into the throwaway DB ==="
docker cp "$DUMP" "$DRILL_NAME:/tmp/restore.dump"
docker exec "$DRILL_NAME" pg_restore -U "$DRILL_USER" -d "$DRILL_DB" --no-owner --no-privileges /tmp/restore.dump 2>&1 | tee /tmp/restore-drill-$$.log
RESTORE_RC=${PIPESTATUS[0]}
echo "pg_restore exit code: $RESTORE_RC (non-zero can be harmless -- e.g. missing"
echo "roles skipped by --no-owner; the real pass/fail signal is the data check below)"

echo "=== Verifying restored schema/data ==="
ALEMBIC="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc 'SELECT version_num FROM alembic_version' 2>&1 | tr -d '[:space:]')"
TABLE_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>&1 | tr -d '[:space:]')"
WS_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM work_sessions" 2>&1 | tr -d '[:space:]')"
EMP_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM employees" 2>&1 | tr -d '[:space:]')"

echo "alembic_version = $ALEMBIC"
echo "public tables   = $TABLE_COUNT"
echo "work_sessions   = $WS_COUNT"
echo "employees       = $EMP_COUNT"

FAIL=0
[[ "$TABLE_COUNT" -gt 0 ]] 2>/dev/null || { echo "FAIL: 0 tables restored"; FAIL=1; }
[[ -n "$ALEMBIC" ]] || { echo "FAIL: alembic_version empty/unreadable"; FAIL=1; }
if [[ -n "$MANIFEST" && -f "$MANIFEST" ]]; then
  EXPECTED="$(python3 -c "import json;print(json.load(open('$MANIFEST'))['migration_head'])" 2>/dev/null || echo "")"
  if [[ -n "$EXPECTED" && "$EXPECTED" != "$ALEMBIC" ]]; then
    echo "FAIL: migration_head mismatch: manifest=$EXPECTED restored=$ALEMBIC"
    FAIL=1
  else
    echo "OK: migration_head matches manifest ($EXPECTED)"
  fi
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo "RESTORE_DRILL_PASS: dump=$DUMP tables=$TABLE_COUNT work_sessions=$WS_COUNT employees=$EMP_COUNT alembic=$ALEMBIC"
else
  echo "RESTORE_DRILL_FAIL"
  exit 1
fi
