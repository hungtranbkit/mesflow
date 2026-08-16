#!/usr/bin/env bash
# Shared constants/helpers for the ProjectFlow contract scripts in this
# directory. Sourced, not executed directly.
set -Eeuo pipefail

PF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PF_COMPOSE_FILE="$PF_ROOT/compose.projectflow-local.yml"
PF_PROJECT="mesflow-projectflow-local"
PF_PORT="${MESFLOW_LOCAL_PORT:-18280}"
PF_ARTIFACTS_DIR="$PF_ROOT/../artifacts/releases"
PF_LATEST_META_DIR="$PF_ROOT/../artifacts/latest"
PF_LATEST_META="$PF_LATEST_META_DIR/mesflow-app.json"

pf_compose() {
  docker compose -f "$PF_COMPOSE_FILE" -p "$PF_PROJECT" "$@"
}

pf_version() {
  tr -d '[:space:]' < "$PF_ROOT/VERSION.txt"
}

pf_latest_release_dir() {
  ls -1dt "$PF_ARTIFACTS_DIR"/*/ 2>/dev/null | grep -v TEMPLATE | head -1 || true
}
