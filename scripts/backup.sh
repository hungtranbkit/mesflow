#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
mkdir -p runtime/backups
ts=$(date +%Y%m%d_%H%M%S)
base="runtime/backups/mesflow_v65_${ts}"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "${base}.dump"
docker compose exec -T postgres pg_restore -l < "${base}.dump" > "${base}.manifest"
sha256sum "${base}.dump" > "${base}.sha256"
tar -czf "${base}_uploads.tar.gz" -C runtime uploads
find runtime/backups -type f -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
echo "${base}.dump"
