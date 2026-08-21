#!/usr/bin/env bash
# MESFlow source-stage installer.
#
# Purpose: copy/update MESFlow SOURCE into the agent workspace only.
# This script intentionally DOES NOT build images, start Docker, migrate the
# database, perform deployment health checks, or change production services.
# Deploy Agent owns the deployment lifecycle after source staging completes.
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_WORKSPACE="${HOME:-/tmp}/workspace/mesflow/mesflow"
TARGET_DIR="${MESFLOW_WORKSPACE_DIR:-$DEFAULT_WORKSPACE}"

usage() {
  cat <<USAGE
Usage: $0 [--target PATH]

Copy/update this MESFlow source release into a workspace only.

  --target PATH   MESFlow app destination (default: ~/workspace/mesflow/mesflow)

Preserved when already present in the workspace:
  .env
  .git/
  .projectflow/
  runtime/
  runtime-projectflow-local/

This command never runs Docker or deploys MESFlow.
After it finishes, continue deployment through Deploy Agent.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="${2:?--target requires PATH}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log(){ printf '[MESFlow source install] %s\n' "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

[[ -f "$SOURCE_DIR/VERSION.txt" ]] || die "VERSION.txt missing from source package"
NEW_VERSION="$(tr -d '[:space:]' < "$SOURCE_DIR/VERSION.txt")"
[[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid VERSION.txt: $NEW_VERSION"

SOURCE_REAL="$(cd "$SOURCE_DIR" && pwd -P)"
mkdir -p "$TARGET_DIR"
TARGET_REAL="$(cd "$TARGET_DIR" && pwd -P)"

# Hard safety boundary: this installer may only stage into a MESFlow project
# directory. The real MESFlow app root is the nested .../mesflow/mesflow.
TARGET_PARENT="$(dirname "$TARGET_REAL")"
[[ "$(basename "$TARGET_REAL")" == "mesflow" ]] || die "unsafe target refused: $TARGET_REAL (basename must be mesflow)"
[[ "$(basename "$TARGET_PARENT")" == "mesflow" ]] || die "unsafe target refused: $TARGET_REAL (expected nested .../mesflow/mesflow)"
[[ "$TARGET_REAL" != "$TARGET_PARENT" ]] || die "unsafe target refused: target equals parent"

if [[ "$SOURCE_REAL" == "$TARGET_REAL" ]]; then
  log "source already is the target workspace: $TARGET_REAL"
  log "READY_FOR_AGENT_DEPLOY version=$NEW_VERSION workspace=$TARGET_REAL"
  exit 0
fi

OLD_VERSION="none"
if [[ -f "$TARGET_DIR/VERSION.txt" ]]; then
  OLD_VERSION="$(tr -d '[:space:]' < "$TARGET_DIR/VERSION.txt")"
fi

log "source version: $NEW_VERSION"
log "workspace version: $OLD_VERSION"
log "workspace: $TARGET_REAL"
log "staging source only; Deploy Agent remains responsible for deployment"

if command -v rsync >/dev/null 2>&1; then
  # Copy source while protecting workspace/runtime state. Deliberately do NOT
  # use rsync --delete: source staging must never remove files from a workspace.
  rsync -a \
    --exclude '.env' \
    --exclude '.git/' \
    --exclude '.projectflow/' \
    --exclude 'runtime/' \
    --exclude 'runtime-projectflow-local/' \
    --exclude 'dist/' \
    --exclude 'artifacts/' \
    "$SOURCE_DIR/" "$TARGET_DIR/"
else
  # Portable fallback. It does not delete obsolete source files, but it still
  # never overwrites persistence or workspace-local agent state.
  (cd "$SOURCE_DIR" && tar \
      --exclude='./.env' \
      --exclude='./.git' \
      --exclude='./.projectflow' \
      --exclude='./runtime' \
      --exclude='./runtime-projectflow-local' \
      --exclude='./dist' \
      --exclude='./artifacts' \
      -cf - .) | (cd "$TARGET_DIR" && tar -xf -)
fi

[[ -f "$TARGET_DIR/VERSION.txt" ]] || die "staged workspace is missing VERSION.txt"
STAGED_VERSION="$(tr -d '[:space:]' < "$TARGET_DIR/VERSION.txt")"
[[ "$STAGED_VERSION" == "$NEW_VERSION" ]] || die "staged version mismatch: expected $NEW_VERSION, got $STAGED_VERSION"
[[ -f "$TARGET_DIR/install.sh" ]] || die "staged workspace is missing install.sh"
[[ -f "$TARGET_DIR/scripts/install.sh" ]] || die "staged workspace is missing scripts/install.sh"

log "source stage complete: $OLD_VERSION -> $NEW_VERSION"
log "no Docker/build/migration/deploy command was executed"
log "READY_FOR_AGENT_DEPLOY version=$NEW_VERSION workspace=$TARGET_REAL"
