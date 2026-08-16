#!/usr/bin/env bash
# ProjectFlow contract: preflight. Read-only checks only -- never installs
# packages, never kills a process/container, never touches production.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

fail=0
check(){ local label="$1"; shift; if "$@" >/dev/null 2>&1; then echo "PASS  $label"; else echo "FAIL  $label"; fail=1; fi; }

echo "===== MESFlow App preflight ====="

check "docker available"          command -v docker
check "docker daemon reachable"   docker info
check "docker compose available"  docker compose version

echo
echo "-- required files --"
for f in VERSION.txt compose.yml compose.projectflow-local.yml Dockerfile requirements.txt; do
  if [[ -f "$PF_ROOT/$f" ]]; then echo "PASS  $f present"; else echo "FAIL  $f missing"; fail=1; fi
done

echo
echo "-- required env variable NAMES (sandbox supplies safe local defaults for all of these; no real secret required) --"
for v in MESFLOW_LOCAL_PORT MESFLOW_IMAGE; do
  echo "INFO  $v (optional, default applied if unset)"
done

echo
echo "-- disk --"
free_kb="$(df -Pk "$PF_ROOT" | awk 'NR==2{print $4}')"
if (( free_kb > 2097152 )); then
  echo "PASS  disk free: ${free_kb} KB (>2GB)"
else
  echo "FAIL  disk free: ${free_kb} KB (<2GB required)"
  fail=1
fi

echo
echo "-- required local sandbox port --"
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${PF_PORT}\$"; then
  owner="$(docker ps --filter "publish=${PF_PORT}" --format '{{.Names}} ({{.Image}})' 2>/dev/null || true)"
  if [[ -n "$owner" ]]; then
    echo "WARN  port ${PF_PORT} already bound by container: $owner"
  else
    echo "WARN  port ${PF_PORT} already bound by a non-Docker process (not auto-killed -- set MESFLOW_LOCAL_PORT to another port or free it manually)"
  fi
else
  echo "PASS  port ${PF_PORT} free"
fi

echo
echo "-- local sandbox compose validity --"
if MESFLOW_IMAGE="${MESFLOW_IMAGE:-mesflow-app:dev}" pf_compose config -q; then
  echo "PASS  compose.projectflow-local.yml config valid"
else
  echo "FAIL  compose.projectflow-local.yml config invalid"
  fail=1
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "PREFLIGHT PASS"
else
  echo "PREFLIGHT FAIL"
  exit 1
fi
