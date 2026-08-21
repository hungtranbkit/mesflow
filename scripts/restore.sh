#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -eq 1 ]] || { echo "Usage: $0 backup.dump"; exit 2; }
backup=$(realpath "$1")
[[ -s "$backup" ]] || { echo 'Backup missing/empty'; exit 1; }
set -a; source .env; set +a
read -r -p "Type RESTORE to replace database ${POSTGRES_DB}: " confirm
[[ "$confirm" == RESTORE ]] || exit 1
bash scripts/backup.sh >/dev/null
docker compose stop mesflow || true
docker compose exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$backup"
docker compose up -d mesflow
bash scripts/regression-test.sh
