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
      # PRODUCTION FROZEN as of 2026-08-25 -- see docs/DEPLOY_ARCHITECTURE_A.md
      # "Production origin investigation". This target used to hardcode
      # SSH_HOST=127.0.0.1 / REMOTE_DIR=/opt/mesflow on the assumption that
      # this dev machine's local copy WAS real production. It is not --
      # confirmed by deploying here and public mesflow.net not changing.
      # Real production's actual host is unconfirmed (best lead:
      # ssh-prod.mesflow.net via Cloudflare Access, user kimex -- not
      # verified, auth not available from this session).
      #
      # Refuse to guess. A real target must be explicitly provided in
      # $PRODUCTION_TARGET_FILE (gitignored -- never commit real prod
      # credentials/host), and that host must NOT resolve to this machine.
      local target_file="${PRODUCTION_TARGET_FILE:-$REPO_ROOT/scripts/production-target.env}"
      if [[ ! -f "$target_file" ]]; then
        echo "PRODUCTION_TARGET_NOT_CONFIGURED" >&2
        echo "No $target_file -- real Production's host is unconfirmed (see" >&2
        echo "docs/DEPLOY_ARCHITECTURE_A.md). Create that file (PRODUCTION_SSH_HOST=" >&2
        echo "/PRODUCTION_SSH_USER=/PRODUCTION_REMOTE_DIR=...) only once the real" >&2
        echo "target is verified -- do not guess it back in." >&2
        exit 1
      fi
      # shellcheck disable=SC1090
      source "$target_file"
      : "${PRODUCTION_SSH_HOST:?PRODUCTION_SSH_HOST missing from $target_file}"
      : "${PRODUCTION_SSH_USER:?PRODUCTION_SSH_USER missing from $target_file}"
      : "${PRODUCTION_REMOTE_DIR:?PRODUCTION_REMOTE_DIR missing from $target_file}"
      case "$PRODUCTION_SSH_HOST" in
        127.0.0.1|localhost|::1|"$(hostname)"|"$(hostname -f 2>/dev/null)")
          echo "PRODUCTION_TARGET_NOT_CONFIGURED" >&2
          echo "PRODUCTION_SSH_HOST in $target_file resolves to THIS machine" >&2
          echo "($PRODUCTION_SSH_HOST) -- refusing. This is the exact mistake that" >&2
          echo "caused the earlier incident. Real production is a different host." >&2
          exit 1
          ;;
      esac
      SSH_HOST="$PRODUCTION_SSH_HOST"
      SSH_USER="$PRODUCTION_SSH_USER"
      REMOTE_DIR="$PRODUCTION_REMOTE_DIR"
      COMPOSE_PROJECT="${PRODUCTION_COMPOSE_PROJECT:-mesflow}"
      APP_SERVICE="${PRODUCTION_APP_SERVICE:-mesflow}"
      APP_CONTAINER="${PRODUCTION_APP_CONTAINER:-mesflow-app}"
      DB_CONTAINER="${PRODUCTION_DB_CONTAINER:-mesflow-postgres}"
      SERVER_ROLE=PRODUCTION
      APP_PORT="${PRODUCTION_APP_PORT:-8080}"
      NETWORK="${PRODUCTION_NETWORK:-mesflow_network}"
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
