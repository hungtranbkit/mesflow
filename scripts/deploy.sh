#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/preflight.sh
[[ -d runtime/postgres-v65 ]] && bash scripts/backup.sh >/dev/null || true
export MESFLOW_DEPLOYMENT_ID=${MESFLOW_DEPLOYMENT_ID:-$(date +%Y%m%d-%H%M%S)}
if grep -q '^MESFLOW_DEPLOYMENT_ID=' .env; then sed -i "s/^MESFLOW_DEPLOYMENT_ID=.*/MESFLOW_DEPLOYMENT_ID=${MESFLOW_DEPLOYMENT_ID}/" .env; else echo "MESFLOW_DEPLOYMENT_ID=${MESFLOW_DEPLOYMENT_ID}" >> .env; fi
docker compose up -d --build postgres mesflow
bash scripts/regression-test.sh
docker compose ps
