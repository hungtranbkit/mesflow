#!/usr/bin/env sh
set -eu

if ! command -v crontab >/dev/null 2>&1; then
  echo "ERROR: 'crontab' is not available on this host -- cannot install the" >&2
  echo "log_retention job. Install cron (e.g. 'apt-get install cron') and" >&2
  echo "re-run this script." >&2
  exit 1
fi

SCHEDULE="${MESFLOW_LOG_RETENTION_CRON:-17 2 * * *}"
ROOT_DIR="${MESFLOW_ROOT:-/opt/mesflow}"
APP_SERVICE="${MESFLOW_APP_SERVICE:-mesflow}"
LINE="$SCHEDULE cd $ROOT_DIR && docker compose exec -T $APP_SERVICE /app/scripts/cleanup-logs.sh run >> runtime/log-retention.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'cleanup-logs.sh' || true; echo "$LINE" ) | crontab -
echo "Installed: $LINE"
