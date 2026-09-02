#!/usr/bin/env bash
# Idempotent, lock-protected, atomic-output DB backup by CONTAINER NAME --
# deliberately does NOT require a mesflow source checkout on the host
# (RULE 6: Production Test/Production never need one). Works identically
# on DEV (workspace checkout present) and on a deployed host (only this
# one file + Docker access needed) as long as the DB/app container names
# match. Never touches the live DB beyond a read-only pg_dump + a few
# read-only COUNT(*) queries for the manifest.
#
# Usage: ./scripts/backup-db.sh
# Env (all optional):
#   POSTGRES_CONTAINER   default mesflow-postgres
#   APP_CONTAINER        default mesflow-app
#   POSTGRES_USER        default mesflow
#   POSTGRES_DB          default mesflow
#   BACKUP_DIR           default <this repo>/runtime/backups (DEV) --
#                        pass an explicit path when running standalone
#                        (no repo checkout) on a deployed host.
#   BACKUP_RETENTION_COUNT  default 14 (keep newest N dump sets FOR THIS
#                        CONTAINER; never deletes down to zero; a dump
#                        with a sibling .verified marker is never deleted
#                        by retention regardless of age -- see
#                        restore-drill.sh, which creates that marker on a
#                        passing drill)
#
# Multi-target safety: every output filename embeds POSTGRES_CONTAINER
# (e.g. mesflow_mesflow-postgres_<ts>.dump vs
# mesflow_mesflow-prodtest-db_<ts>.dump), and both the lock file and the
# retention glob are scoped to that same container name -- two different
# DB targets backing up into the SAME BACKUP_DIR on the same host (e.g.
# DEV's mesflow-postgres and PROD-TEST's mesflow-prodtest-db, both on
# this machine) never block or prune each other.
set -Eeuo pipefail
umask 077   # backup dumps may contain real business/PII data -- private by default

CONTAINER="${POSTGRES_CONTAINER:-mesflow-postgres}"
APP_CONTAINER="${APP_CONTAINER:-mesflow-app}"
DB_USER="${POSTGRES_USER:-mesflow}"
DB_NAME="${POSTGRES_DB:-mesflow}"
if [[ -n "${BACKUP_DIR:-}" ]]; then
  OUT_DIR="$BACKUP_DIR"
else
  OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/runtime/backups"
fi
RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-14}"
die(){ echo "ERROR: $*" >&2; exit 1; }

[[ "$RETENTION_COUNT" =~ ^[0-9]+$ ]] || die "BACKUP_RETENTION_COUNT must be a non-negative integer, got: '$RETENTION_COUNT'"
command -v docker >/dev/null || die "DOCKER_NOT_FOUND"
docker inspect "$CONTAINER" >/dev/null 2>&1 || die "CONTAINER_NOT_FOUND: $CONTAINER"

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR" 2>/dev/null || true

# --- Concurrency guard, scoped per DB container: two targets backing up
# to the same BACKUP_DIR never block each other; two runs for the SAME
# target never overlap. ---
LOCK_PATH="$OUT_DIR/.backup-${CONTAINER}.lock"
exec {LOCK_FD}>"$LOCK_PATH"
flock -n "$LOCK_FD" || die "BACKUP_BUSY: another backup-db.sh run for $CONTAINER holds the lock ($LOCK_PATH)"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
base="$OUT_DIR/mesflow_${CONTAINER}_${ts}"
tmp="${base}.dump.tmp"

# --- Clean up a half-written .tmp on ANY failure (die, pg_dump error,
# Ctrl-C) -- never leave partial output where retention/other tooling
# could mistake it for a real dump (it never matches the *.dump glob
# below, but a stray large .tmp file is still worth not leaving behind).
cleanup_tmp(){ [[ -f "$tmp" ]] && rm -f "$tmp"; }
trap cleanup_tmp EXIT

# --- Atomic output: pg_dump writes to a .tmp path; only renamed into its
# final name after a successful, complete dump. A reader can never see a
# half-written .dump file. ---
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$tmp"
mv -f "$tmp" "${base}.dump"
trap - EXIT   # the real .dump now exists; nothing left for cleanup_tmp to do
chmod 600 "${base}.dump"
sha256sum "${base}.dump" | awk '{print $1}' > "${base}.dump.sha256"
chmod 600 "${base}.dump.sha256"

# --- Manifest: version/migration/source identity needed to know what a
# given dump corresponds to (never secrets: no password/token/URL), PLUS
# a curated snapshot of key table row counts taken immediately after the
# dump (same script, sequential queries -- not a perfectly atomic
# point-in-time match with pg_dump's own MVCC snapshot on a live system,
# but close enough to catch a truncated/partial restore, which is this
# manifest's actual job; restore-drill.sh compares a RESTORED dump's
# counts against THESE frozen numbers, never against the live DB again). ---
app_version="$(docker exec "$APP_CONTAINER" cat /app/VERSION.txt 2>/dev/null || echo unknown)"
app_image="$(docker inspect "$APP_CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || echo unknown)"
migration_head="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '[:space:]' || echo unknown)"
table_count="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null | tr -d '[:space:]' || echo 0)"
# work_sessions/employees are core MESFlow tables expected to exist on
# every real deployment; a missing table here (0 vs an error) is itself
# useful restore-integrity signal, so failures are coerced to 0 rather
# than aborting the whole backup over a read-only count query.
work_sessions_count="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM work_sessions" 2>/dev/null | tr -d '[:space:]' || echo 0)"
employees_count="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM employees" 2>/dev/null | tr -d '[:space:]' || echo 0)"
dump_sha256="$(cat "${base}.dump.sha256")"
dump_bytes="$(stat -c%s "${base}.dump" 2>/dev/null || stat -f%z "${base}.dump" 2>/dev/null || echo 0)"
cat > "${base}.manifest.json" <<EOF
{
  "backup_utc": "${ts}",
  "db_container": "${CONTAINER}",
  "db_name": "${DB_NAME}",
  "app_container": "${APP_CONTAINER}",
  "app_version": "${app_version}",
  "app_image": "${app_image}",
  "migration_head": "${migration_head}",
  "dump_file": "$(basename "${base}.dump")",
  "dump_sha256": "${dump_sha256}",
  "dump_bytes": ${dump_bytes},
  "snapshot_counts": {
    "note": "queried immediately after pg_dump, not inside its own MVCC snapshot -- a sanity/restore-integrity signal, not a guaranteed exact point-in-time match on a live system",
    "public_tables": ${table_count:-0},
    "work_sessions": ${work_sessions_count:-0},
    "employees": ${employees_count:-0}
  }
}
EOF
chmod 600 "${base}.manifest.json"

# --- Retention: keep the newest N dump sets FOR THIS CONTAINER by count
# (not just age -- disk-appropriate on a small host), always leaves at
# least 1 regardless of RETENTION_COUNT, never deletes a set with a
# sibling .verified marker (restore-drill.sh writes this on a passing
# drill) even if older than the keep window, and only deletes a FULL set
# (dump+sha256+manifest[+verified]) together so nothing is ever orphaned. ---
keep_count="$RETENTION_COUNT"
[[ "$keep_count" -lt 1 ]] && keep_count=1
mapfile -t all_dumps < <(ls -1t "$OUT_DIR"/mesflow_"${CONTAINER}"_*.dump 2>/dev/null || true)
if [[ "${#all_dumps[@]}" -gt "$keep_count" ]]; then
  for old in "${all_dumps[@]:$keep_count}"; do
    stem="${old%.dump}"
    if [[ -f "${stem}.verified" ]]; then
      echo "RETENTION: keeping $(basename "$old") -- has a .verified restore-drill marker"
      continue
    fi
    rm -f "${stem}.dump" "${stem}.dump.sha256" "${stem}.manifest.json"
    echo "RETENTION: removed $(basename "$old") (+ .sha256/.manifest.json)"
  done
fi

echo "BACKUP_OK: ${base}.dump (sha256=${dump_sha256}, ${dump_bytes} bytes)"
echo "MANIFEST: ${base}.manifest.json"
