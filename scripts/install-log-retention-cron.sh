#!/usr/bin/env sh
set -eu
SCHEDULE="${MESFLOW_LOG_RETENTION_CRON:-17 2 * * *}"
ROOT_DIR="${MESFLOW_ROOT:-/opt/mesflow}"
LINE="$SCHEDULE cd $ROOT_DIR && docker compose exec -T mesflow /app/scripts/cleanup-logs.sh run >> runtime/log-retention.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'cleanup-logs.sh' || true; echo "$LINE" ) | crontab -
echo "Installed: $LINE"
