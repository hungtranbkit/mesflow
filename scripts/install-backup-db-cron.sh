#!/usr/bin/env sh
# Installs a daily DB backup cron entry running scripts/backup-db.sh, with
# EVERY relevant env var baked directly into the cron line itself (cron
# runs with a minimal environment -- it does NOT inherit the interactive
# shell's exported vars this installer happened to be run under, so
# backup-db.sh's own defaults, not this shell's, would otherwise apply at
# 02:17 every night regardless of what was used for a manual test run).
#
# Multi-target safe: the idempotent replace marker is scoped to
# POSTGRES_CONTAINER (a dedicated "# mesflow-backup-db:<container>"
# comment line immediately above each managed cron line), NOT a blanket
# match on the script name -- installing this for a second DB target
# (e.g. DEV's mesflow-postgres and PROD-TEST's mesflow-prodtest-db, both
# reachable from the same host) replaces only that target's own prior
# entry and leaves every other cron line (this job's other targets, or
# anything unrelated a human/other tool installed) untouched.
#
# Usage: ./scripts/install-backup-db-cron.sh
#   POSTGRES_CONTAINER    default mesflow-postgres (also the target-scope
#                         key for the idempotent marker above)
#   APP_CONTAINER         default mesflow-app
#   POSTGRES_USER         default mesflow
#   POSTGRES_DB           default mesflow
#   BACKUP_DIR            REQUIRED when installing standalone (no repo
#                         checkout) on a deployed host -- backup-db.sh's
#                         own relative default only makes sense with a
#                         checkout present.
#   BACKUP_RETENTION_COUNT  passed through if set
#   BACKUP_DB_SCRIPT_PATH  default: this script's own sibling
#                         backup-db.sh, absolute path
#   BACKUP_DB_CRON         default "17 2 * * *" (02:17 daily)
set -eu

SCRIPT_PATH="${BACKUP_DB_SCRIPT_PATH:-$(cd "$(dirname "$0")" && pwd)/backup-db.sh}"
[ -f "$SCRIPT_PATH" ] || { echo "ERROR: backup-db.sh not found at $SCRIPT_PATH" >&2; exit 1; }
CRON_SCHEDULE="${BACKUP_DB_CRON:-17 2 * * *}"
CONTAINER="${POSTGRES_CONTAINER:-mesflow-postgres}"
APP_CONTAINER_V="${APP_CONTAINER:-mesflow-app}"
DB_USER="${POSTGRES_USER:-mesflow}"
DB_NAME="${POSTGRES_DB:-mesflow}"
BACKUP_DIR_V="${BACKUP_DIR:-$(dirname "$SCRIPT_PATH")/../runtime/backups}"
RETENTION_V="${BACKUP_RETENTION_COUNT:-}"

if ! command -v crontab >/dev/null 2>&1; then
  echo "ERROR: 'crontab' is not available on this host -- cannot install the" >&2
  echo "backup-db.sh cron job." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR_V"

# Minimal, safe single-quote escaping for cron-line env values (wraps in
# single quotes, escaping any embedded single quote as '\'' -- standard
# POSIX shell quoting trick). Every value baked into the line goes through
# this, never interpolated raw.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

MARKER="# mesflow-backup-db:${CONTAINER}"
ENV_PREFIX="BACKUP_DIR=$(sq "$BACKUP_DIR_V") POSTGRES_CONTAINER=$(sq "$CONTAINER") APP_CONTAINER=$(sq "$APP_CONTAINER_V") POSTGRES_USER=$(sq "$DB_USER") POSTGRES_DB=$(sq "$DB_NAME")"
if [ -n "$RETENTION_V" ]; then
  ENV_PREFIX="$ENV_PREFIX BACKUP_RETENTION_COUNT=$(sq "$RETENTION_V")"
fi
LINE="$CRON_SCHEDULE $ENV_PREFIX bash $(sq "$SCRIPT_PATH") >> $(sq "$BACKUP_DIR_V/backup-${CONTAINER}.log") 2>&1"

# Idempotent replace scoped to this target only: strip any previous
# "$MARKER" line and the line immediately following it (the cron entry it
# introduced), then append the fresh pair. Every other existing crontab
# line -- other targets' marker+line pairs included -- passes through
# unmodified.
OLD="$(crontab -l 2>/dev/null || true)"
NEW="$(printf '%s\n' "$OLD" | awk -v marker="$MARKER" '
  $0 == marker { skip = 1; next }
  skip > 0 { skip--; next }
  { print }
')"
printf '%s\n%s\n%s\n' "$NEW" "$MARKER" "$LINE" | sed '/^$/d' | crontab -

echo "Installed for container=$CONTAINER:"
echo "$MARKER"
echo "$LINE"
