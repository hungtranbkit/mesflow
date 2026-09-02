#!/usr/bin/env sh
# Installs a daily DB backup cron entry running scripts/backup-db.sh.
# Idempotent: any existing line for this job (matched by its own command
# substring) is replaced, never duplicated; every OTHER existing crontab
# line is left untouched. Same model as install-reconcile-cron.sh.
#
# Usage: ./scripts/install-backup-db-cron.sh
#   BACKUP_DB_SCRIPT_PATH  default: this script's own sibling backup-db.sh,
#                          absolute path (so it works even when this repo
#                          isn't checked out on the target host -- see
#                          backup-db.sh's own header for why it's
#                          self-contained). MUST be set explicitly when
#                          installing standalone (no repo checkout).
#   BACKUP_DB_CRON         default "17 2 * * *" (02:17 daily, same slot
#                          the older per-repo backup.sh/install-backup-cron.sh
#                          used)
#   BACKUP_DIR             passed through as env for backup-db.sh; default
#                          left to backup-db.sh's own default if unset here
set -eu

SCRIPT_PATH="${BACKUP_DB_SCRIPT_PATH:-$(cd "$(dirname "$0")" && pwd)/backup-db.sh}"
[ -f "$SCRIPT_PATH" ] || { echo "ERROR: backup-db.sh not found at $SCRIPT_PATH" >&2; exit 1; }
CRON_SCHEDULE="${BACKUP_DB_CRON:-17 2 * * *}"
LOG_DIR="${BACKUP_DIR:-$(dirname "$SCRIPT_PATH")/../runtime/backups}"

if ! command -v crontab >/dev/null 2>&1; then
  echo "ERROR: 'crontab' is not available on this host -- cannot install the" >&2
  echo "backup-db.sh cron job." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
LINE="$CRON_SCHEDULE bash $SCRIPT_PATH >> $LOG_DIR/backup.log 2>&1"
(
  crontab -l 2>/dev/null | grep -vF "backup-db.sh" || true
  echo "$LINE"
) | crontab -
echo "Installed: $LINE"
