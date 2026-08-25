#!/usr/bin/env bash
# Shared config/helpers for release-build.sh / deploy.sh / deploy-status.sh /
# deploy-rollback.sh. Source, don't execute.
set -euo pipefail

REGISTRY="127.0.0.1:5000"
IMAGE_NAME="mesflow-app"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$REPO_ROOT/release"

# target_config <target>: sets SSH_HOST SSH_USER REMOTE_DIR COMPOSE_PROJECT
# APP_SERVICE APP_CONTAINER DB_CONTAINER SERVER_ROLE APP_PORT NETWORK
target_config() {
  case "$1" in
    prodtest)
      SSH_HOST=127.0.0.1
      SSH_USER=dell
      REMOTE_DIR=/home/dell/deploy/mesflow-prodtest
      COMPOSE_PROJECT=mesflow-prodtest
      APP_SERVICE=mesflow-prodtest-app
      APP_CONTAINER=mesflow-prodtest-app
      DB_CONTAINER=mesflow-prodtest-db
      SERVER_ROLE=PRODUCTION_TEST
      APP_PORT=8299
      NETWORK=mesflow-prodtest-net
      ;;
    production)
      SSH_HOST=127.0.0.1
      SSH_USER=dell
      REMOTE_DIR=/opt/mesflow
      COMPOSE_PROJECT=mesflow
      APP_SERVICE=mesflow
      APP_CONTAINER=mesflow-app
      DB_CONTAINER=mesflow-postgres
      SERVER_ROLE=PRODUCTION
      APP_PORT=8080
      NETWORK=mesflow_network
      ;;
    *)
      echo "Unknown target: $1 (expected: prodtest | production)" >&2
      exit 1
      ;;
  esac
}

ssh_target() {
  # ssh_target <ignored -- kept for call-site readability> <command...>
  shift
  ssh -o BatchMode=yes -o ConnectTimeout=5 "${SSH_USER}@${SSH_HOST}" "$@"
}

# Resolve a version string or an explicit digest ref to a full
# registry/image@sha256:... ref, using the release manifest written by
# release-build.sh.
running_digest() {
  # running_digest <container-name> -- the digest of the IMAGE a container
  # is running, not the container itself (containers have no .RepoDigests).
  local cid img
  cid="$1"
  img="$(ssh_target x "docker inspect --format='{{.Image}}' ${cid}" 2>/dev/null || true)"
  [[ -z "$img" ]] && return 0
  ssh_target x "docker image inspect --format='{{index .RepoDigests 0}}' ${img}" 2>/dev/null || true
}

resolve_image_ref() {
  local ver_or_digest="$1"
  if [[ "$ver_or_digest" == *"@sha256:"* ]]; then
    echo "$ver_or_digest"
    return
  fi
  local manifest="$RELEASE_DIR/mesflow-${ver_or_digest}.json"
  if [[ ! -f "$manifest" ]]; then
    echo "No release manifest for version '$ver_or_digest' at $manifest -- run release-build.sh first, or pass a full @sha256 digest ref." >&2
    exit 1
  fi
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['digest'])" "$manifest"
}
