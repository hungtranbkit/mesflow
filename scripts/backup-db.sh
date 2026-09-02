#!/usr/bin/env bash
# Idempotent, lock-protected, atomic-output DB backup by CONTAINER NAME --
# deliberately does NOT require a mesflow source checkout on the host
# (RULE 6: Production Test/Production never need one). Works identically
# on DEV (workspace checkout present) and on a deployed host (only this
# one file + Docker access needed) as long as the DB/app container names
# match. Never touches the live DB beyond a read-only pg_dump.
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
#   BACKUP_RETENTION_COUNT  default 14 (keep newest N dump sets; never
#                        deletes down to zero -- always keeps at least 1)
set -Eeuo pipefail

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

command -v docker >/dev/null || die "DOCKER_NOT_FOUND"
docker inspect "$CONTAINER" >/dev/null 2>&1 || die "CONTAINER_NOT_FOUND: $CONTAINER"

mkdir -p "$OUT_DIR"

# --- Concurrency guard: never run two backups at once (idempotent-safe:
# a second invocation while one is in flight fails fast rather than
# racing on the same lockfile/output dir). ---
exec {LOCK_FD}>"$OUT_DIR/.backup.lock"
flock -n "$LOCK_FD" || die "BACKUP_BUSY: another backup-db.sh run holds the lock ($OUT_DIR/.backup.lock)"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
base="$OUT_DIR/mesflow_${ts}"
tmp="${base}.dump.tmp"

# --- Atomic output: pg_dump writes to a .tmp path; only renamed into its
# final name after a successful, complete dump. A reader can never see a
# half-written .dump file. ---
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$tmp"
mv -f "$tmp" "${base}.dump"
sha256sum "${base}.dump" | awk '{print $1}' > "${base}.dump.sha256"

# --- Manifest: version/migration/source identity needed to know what a
# given dump corresponds to -- never secrets (no password/token/URL). ---
app_version="$(docker exec "$APP_CONTAINER" cat /app/VERSION.txt 2>/dev/null || echo unknown)"
app_image="$(docker inspect "$APP_CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || echo unknown)"
migration_head="$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '[:space:]' || echo unknown)"
dump_sha256="$(cat "${base}.dump.sha256")"
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
  "dump_sha256": "${dump_sha256}"
}
EOF

# --- Retention: keep the newest N dump sets by count (not just age --
# disk-appropriate on a small host), always leaves at least 1 regardless
# of RETENTION_COUNT, and only deletes a FULL set (dump+sha256+manifest)
# together so no orphaned manifest ever outlives its dump. ---
keep_count="$RETENTION_COUNT"
[[ "$keep_count" -lt 1 ]] && keep_count=1
mapfile -t all_dumps < <(ls -1t "$OUT_DIR"/mesflow_*.dump 2>/dev/null || true)
if [[ "${#all_dumps[@]}" -gt "$keep_count" ]]; then
  for old in "${all_dumps[@]:$keep_count}"; do
    stem="${old%.dump}"
    rm -f "${stem}.dump" "${stem}.dump.sha256" "${stem}.manifest.json"
    echo "RETENTION: removed $(basename "$old") (+ .sha256/.manifest.json)"
  done
fi

echo "BACKUP_OK: ${base}.dump (sha256=${dump_sha256})"
echo "MANIFEST: ${base}.manifest.json"
