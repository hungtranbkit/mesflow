#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BASE_URL="${BASE_URL:-https://127.0.0.1}"
CURL=(curl -kfsS -H 'Host: mesflow.net')
"${CURL[@]}" "$BASE_URL/nginx-health"
"${CURL[@]}" "$BASE_URL/api/system/health"
"${CURL[@]}" "$BASE_URL/api/system/ready"
"${CURL[@]}" "$BASE_URL/api/system/version"
echo "MESFlow v65 production smoke test passed"
