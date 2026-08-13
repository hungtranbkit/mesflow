#!/usr/bin/env bash
set -Eeuo pipefail
echo "MESFlow image deploy preflight"
command -v docker >/dev/null && echo "Docker PASS" || { echo "Docker FAIL"; exit 1; }
docker info >/dev/null && echo "Docker daemon PASS" || { echo "Docker daemon FAIL"; exit 1; }
[[ -n "${MESFLOW_IMAGE:-}" ]] && echo "MESFLOW_IMAGE PASS" || echo "MESFLOW_IMAGE WARN (Agent release supplies it)"
df -P . | awk 'NR==2 {print "Disk available: "$4" KB"}'
