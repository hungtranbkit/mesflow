#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
line="17 2 * * * cd $root && bash scripts/backup.sh >> runtime/backups/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'mesflow_v65.*backup.sh' || true; echo "$line" ) | crontab -
echo "$line"
