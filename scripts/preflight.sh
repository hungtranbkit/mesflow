#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null
[[ -f .env ]] || { echo '.env missing'; exit 1; }
docker compose config -q
mkdir -p runtime/{postgres-v65,backups,uploads,reports}
free_kb=$(df -Pk . | awk 'NR==2{print $4}')
(( free_kb > 2097152 )) || { echo 'Need at least 2GB free disk'; exit 1; }
[[ -f certs/mesflow.net.pem ]] || { echo 'Missing certs/mesflow.net.pem'; exit 1; }
[[ -f certs/mesflow.net.key ]] || { echo 'Missing certs/mesflow.net.key'; exit 1; }
echo 'PRECHECK PASS'
