#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-.}"
cd "$REPO"
fail=0
check() {
  local msg="$1"; shift
  if "$@"; then printf '[OK] %s\n' "$msg"; else printf '[FAIL] %s\n' "$msg"; fail=1; fi
}
check "agent server_name exists" grep -q 'server_name agent\.mesflow\.net;' nginx/nginx.conf
check "agent upstream exists" grep -q 'upstream mesflow_agent_backend' nginx/nginx.conf
check "agent points to host:8090" grep -q 'server host\.docker\.internal:8090;' nginx/nginx.conf
check "websocket Upgrade header exists" grep -q 'proxy_set_header Upgrade \$http_upgrade;' nginx/nginx.conf
check "long read timeout exists" grep -q 'proxy_read_timeout 3600s;' nginx/nginx.conf
check "Linux host gateway exists" grep -q 'host\.docker\.internal:host-gateway' compose.yml
check "version is 65.8.44.12" test "$(tr -d '\r\n' < VERSION.txt)" = '65.8.44.12'
if command -v docker >/dev/null 2>&1; then
  docker compose config >/dev/null && printf '[OK] docker compose config valid\n' || { printf '[FAIL] docker compose config invalid\n'; fail=1; }
fi
if command -v python >/dev/null 2>&1 && python -c 'import pytest' >/dev/null 2>&1; then
  python -m pytest -q tests/test_agent_nginx_contract_v6584412.py || fail=1
fi
exit "$fail"
