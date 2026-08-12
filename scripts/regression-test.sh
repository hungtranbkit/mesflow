#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BASE_URL="${BASE_URL:-https://127.0.0.1}"
CURL=(curl -kfsS -H 'Host: mesflow.net')
mkdir -p runtime/reports
"${CURL[@]}" "$BASE_URL/api/system/health" | tee runtime/reports/health.json
"${CURL[@]}" "$BASE_URL/api/system/ready" | tee runtime/reports/ready.json
"${CURL[@]}" "$BASE_URL/api/system/monitoring" | tee runtime/reports/monitoring.json
"${CURL[@]}" "$BASE_URL/api/master/health" | tee runtime/reports/master.json
"${CURL[@]}" "$BASE_URL/api/execution/health" | tee runtime/reports/execution.json
"${CURL[@]}" "$BASE_URL/api/analytics/health" | tee runtime/reports/analytics.json
echo "MESFlow v65 production regression passed"
