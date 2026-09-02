#!/usr/bin/env bash
# Restore-drill: proves a backup-db.sh dump actually restores, on a
# throwaway Postgres container -- NEVER touches the real/live DB.
#
# Safety: the temp container uses a Docker-managed (unnamed, ephemeral)
# volume, not a host bind-mount, and a name that can never collide with
# any real MESFlow container. Always torn down -- container AND its
# anonymous volume (`docker rm -f -v`, scoped to only the volume(s) owned
# by this one container; never a volume prune) -- in a trap, on every
# exit path (pass, fail, or interrupted), after evidence is captured.
#
# Usage: ./scripts/restore-drill.sh <path-to-dump> <manifest.json>
# The manifest is REQUIRED (not optional): this drill's whole point is
# comparing the restore against the FROZEN counts recorded at backup
# time, not the live DB (which may have changed since) and not just
# "some numbers came back non-zero". A missing/unreadable/malformed
# manifest, or a dump whose sha256 doesn't match the manifest, is a hard
# FAIL -- fails closed, never silently skips a check and prints OK.
set -Eeuo pipefail

DUMP="${1:?Usage: restore-drill.sh <path-to-dump> <manifest.json>}"
MANIFEST="${2:?Usage: restore-drill.sh <path-to-dump> <manifest.json> -- manifest is required, not optional (see header)}"
die(){ echo "RESTORE_DRILL_FAIL: $*" >&2; exit 1; }

[[ -f "$DUMP" ]] || die "dump not found: $DUMP"
[[ -f "$MANIFEST" ]] || die "manifest not found: $MANIFEST"

# --- Safe, fail-closed JSON parsing: a single python3 call reads every
# field it needs and prints them newline-delimited; ANY missing/malformed
# field or invalid JSON aborts the whole script (non-zero exit) instead
# of silently substituting an empty string that a later check could
# mistake for "nothing to verify, so OK". ---
MANIFEST_FIELDS="$(python3 - "$MANIFEST" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    m = json.load(f)
required = ['dump_sha256', 'migration_head']
for key in required:
    if not m.get(key):
        raise SystemExit(f'manifest missing required field: {key}')
counts = m.get('snapshot_counts') or {}
for key in ('public_tables', 'work_sessions', 'employees'):
    if key not in counts:
        raise SystemExit(f'manifest missing required snapshot_counts field: {key}')
print(m['dump_sha256'])
print(m['migration_head'])
print(counts['public_tables'])
print(counts['work_sessions'])
print(counts['employees'])
PY
)" || die "manifest is malformed or missing required fields: $MANIFEST"
{
  read -r EXPECTED_SHA256
  read -r EXPECTED_MIGRATION
  read -r EXPECTED_TABLES
  read -r EXPECTED_WS
  read -r EXPECTED_EMP
} <<< "$MANIFEST_FIELDS"

# --- Verify the dump's integrity BEFORE restoring it -- a corrupted or
# swapped file must never silently "restore" as if it were the real one. ---
ACTUAL_SHA256="$(sha256sum "$DUMP" | awk '{print $1}')"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || die "dump checksum mismatch: expected=$EXPECTED_SHA256 actual=$ACTUAL_SHA256 -- refusing to restore a dump that doesn't match its manifest"
echo "OK: dump sha256 matches manifest ($ACTUAL_SHA256)"

DRILL_NAME="mesflow-restore-drill-$(date +%s)-$$"
DRILL_DB="drill"
DRILL_USER="drill"
DRILL_PASSWORD="drill-local-only-$(date +%s)"

cleanup() {
  # -v removes the anonymous volume(s) this specific container owns --
  # never a general `docker volume prune`, which could touch unrelated
  # volumes on a shared host.
  docker rm -f -v "$DRILL_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "=== Starting throwaway Postgres ($DRILL_NAME, ephemeral volume, no host mount) ==="
docker run -d --name "$DRILL_NAME" \
  -e POSTGRES_DB="$DRILL_DB" -e POSTGRES_USER="$DRILL_USER" -e POSTGRES_PASSWORD="$DRILL_PASSWORD" \
  postgres:17-alpine >/dev/null

echo "=== Waiting for it to accept connections ==="
# The official postgres image starts TWICE on a fresh container: a
# temporary internal server (to run initdb/init scripts) that it then
# deliberately shuts down, followed by the real, final server. A plain
# pg_isready loop can catch that first, temporary server -- found live:
# pg_restore then failed with "FATAL: the database system is shutting
# down" because the container moved into its shutdown-for-restart phase
# between pg_isready succeeding and pg_restore actually connecting.
# Waiting for "database system is ready to accept connections" to appear
# TWICE in the container's own logs is the standard, race-free signal
# that the final server (not the disposable init one) is up.
ready=0
for _ in $(seq 1 60); do
  count="$(docker logs "$DRILL_NAME" 2>&1 | grep -c 'database system is ready to accept connections' || true)"
  if [[ "$count" -ge 2 ]]; then ready=1; break; fi
  sleep 1
done
[[ "$ready" -eq 1 ]] || die "drill Postgres never reached its final ready state (saw ${count:-0}/2 'ready to accept connections' log lines)"
# Belt-and-suspenders: also confirm it actually accepts a connection right
# now (the log-count signal alone proves the final server STARTED, this
# proves it's still up this instant).
docker exec "$DRILL_NAME" pg_isready -U "$DRILL_USER" -d "$DRILL_DB" >/dev/null 2>&1 || die "drill Postgres logged final startup but pg_isready still fails"

echo "=== Restoring $DUMP into the throwaway DB ==="
docker cp "$DUMP" "$DRILL_NAME:/tmp/restore.dump"
# --exit-on-error makes pg_restore itself stop at the FIRST real error
# instead of continuing past it -- its exit code is then a trustworthy
# pass/fail signal on its own, not something to wave off as "harmless
# warnings" the way a --no-owner run without this flag can produce.
if ! docker exec "$DRILL_NAME" pg_restore -U "$DRILL_USER" -d "$DRILL_DB" --no-owner --no-privileges --exit-on-error /tmp/restore.dump 2>&1 | tee "/tmp/restore-drill-$$.log"; then
  die "pg_restore failed (--exit-on-error stopped at the first real error) -- see /tmp/restore-drill-$$.log"
fi
echo "OK: pg_restore completed with --exit-on-error (no error stopped it)"

echo "=== Verifying restored schema/data against the manifest's FROZEN snapshot (never the live DB) ==="
ALEMBIC="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc 'SELECT version_num FROM alembic_version' 2>&1 | tr -d '[:space:]')"
TABLE_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>&1 | tr -d '[:space:]')"
WS_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM work_sessions" 2>&1 | tr -d '[:space:]')"
EMP_COUNT="$(docker exec "$DRILL_NAME" psql -U "$DRILL_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM employees" 2>&1 | tr -d '[:space:]')"

FAIL=0
[[ "$ALEMBIC" == "$EXPECTED_MIGRATION" ]] || { echo "FAIL: migration_head mismatch: manifest=$EXPECTED_MIGRATION restored=$ALEMBIC"; FAIL=1; }
[[ "$TABLE_COUNT" == "$EXPECTED_TABLES" ]] || { echo "FAIL: public table count mismatch: manifest=$EXPECTED_TABLES restored=$TABLE_COUNT"; FAIL=1; }
[[ "$WS_COUNT" == "$EXPECTED_WS" ]] || { echo "FAIL: work_sessions count mismatch: manifest=$EXPECTED_WS restored=$WS_COUNT"; FAIL=1; }
[[ "$EMP_COUNT" == "$EXPECTED_EMP" ]] || { echo "FAIL: employees count mismatch: manifest=$EXPECTED_EMP restored=$EMP_COUNT"; FAIL=1; }

if [[ "$FAIL" -ne 0 ]]; then
  die "restored data does not match the manifest's frozen snapshot (see FAIL lines above)"
fi

echo "OK: migration_head=$ALEMBIC, public_tables=$TABLE_COUNT, work_sessions=$WS_COUNT, employees=$EMP_COUNT -- all match the manifest snapshot exactly"

# Mark the source dump as drill-verified so backup-db.sh's retention never
# deletes it, regardless of age/count -- a proven-restorable backup is
# always worth keeping over an unverified newer one.
: > "${DUMP%.dump}.verified"
echo "RESTORE_DRILL_PASS: dump=$DUMP marked ${DUMP%.dump}.verified"
