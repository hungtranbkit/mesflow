#!/bin/sh
# Safe, idempotent recreate for a docker-compose service with an explicit
# container_name. Runs INSIDE mesflow-deploy-agent on mesflow.net-host
# (docker-outside-of-docker: that container has docker CLI + socket
# access to the real host). Reach it from a dev machine like this
# (mirrors exactly how this script was built/tested, 2026-09-02):
#   scp scripts/safe-recreate.sh <remote-host>:/tmp/safe-recreate.sh
#   ssh <remote-host> "docker cp /tmp/safe-recreate.sh mesflow-deploy-agent:/tmp/safe-recreate.sh \
#     && docker exec -u root mesflow-deploy-agent chmod +x /tmp/safe-recreate.sh"
#   ssh <remote-host> "docker exec -u root mesflow-deploy-agent \
#     /tmp/safe-recreate.sh /opt/mesflow mesflow-app mesflow <expected-image>"
# (For prod.mesflow.net:8299 / other directly-reachable hosts, use
# mesflow/scripts/deploy.sh instead -- it already does the equivalent
# --no-deps recreate plus migration-aware rollback; this script exists
# specifically for the docker-outside-of-docker target that tool doesn't
# reach.)
#
# Root cause this exists to prevent (found live, 2026-09-02, two real
# outages this session): `docker compose up -d --force-recreate <service>`
# left a stray, never-renamed hash-named container (e.g.
# "5961ca59de8c_mesflow-app") holding a partial state after a client-side
# `timeout` killed an earlier attempt mid-recreate. Every subsequent
# --force-recreate attempt then failed with "Conflict: name already in
# use" trying to allocate the SAME real name, and one recovery path
# (docker exec -d backgrounding, still using --force-recreate) left the
# whole stack (app AND postgres) down for a period rather than merely
# conflicted.
#
# Fix, in order:
# 1) Preflight: remove any STRAY container matching the service's real
#    name that is NOT actually the currently-attached one (i.e. any
#    "<hash>_<name>" temp-named leftover, or the real name itself if it's
#    sitting in a dead/Created-but-never-started state) -- these are, by
#    construction, never the live service.
# 2) `docker compose up -d --no-deps <service>` -- no --force-recreate.
#    Compose's own config-hash change detection already recreates a
#    service whose image changed; --force-recreate adds no correctness
#    benefit for a routine image bump and only adds the more aggressive,
#    collision-prone teardown/rename path implicated above. --no-deps is
#    load-bearing too: omitting it is the separately-confirmed cause of
#    mesflow-prodtest-db recreating unexpectedly during an unrelated
#    app-only .env change earlier the same day (a plain `up -d` without
#    --no-deps re-evaluates every dependency's config hash, not just the
#    target service's).
# 3) Poll for healthy with a real, generous timeout (this script blocks
#    until done -- it is meant to be invoked via `docker exec -d` or a
#    background job, never killed mid-flight by a short client timeout).
#
# Usage: safe-recreate.sh <compose_dir> <container_name> <compose_service> [expected_image]
set -eu
DIR="${1:?compose dir required}"
NAME="${2:?container_name required}"
SERVICE="${3:?compose_service required}"
EXPECTED_IMAGE="${4:-}"

cd "$DIR"

echo "== preflight: stray containers matching '$NAME' =="
docker ps -a --format '{{.Names}}\t{{.ID}}\t{{.Status}}' | grep -E "(^|_)${NAME}(\$|_)" || echo "(none)"
for cid in $(docker ps -a --format '{{.Names}} {{.ID}}' | awk -v n="$NAME" '$1 != n && index($1, n) { print $2 }'); do
  echo "removing stray container $cid"
  docker rm -f "$cid" 2>&1 || true
done
# The real name itself, if present but not actually running (a previous
# attempt got as far as "Created" and no further):
state="$(docker inspect "$NAME" --format '{{.State.Status}}' 2>/dev/null || echo absent)"
if [ "$state" != "absent" ] && [ "$state" != "running" ]; then
  echo "removing non-running '$NAME' (state=$state) before recreate"
  docker rm -f "$NAME" 2>&1 || true
fi

echo "== docker compose up -d --no-deps $NAME (no --force-recreate) =="
# --no-deps: root-caused live (2026-09-02) that omitting this is exactly
# what caused mesflow-prodtest-db to recreate unexpectedly on prod.mesflow.net
# during an unrelated app-only .env change -- scripts/deploy.sh (this
# project's own more mature Architecture-A tool, prodtest/production
# targets) already uses this exact `--no-deps` + no --force-recreate
# pattern; this script matches it for the mesflow.net-host target that
# tool doesn't cover (reached via docker-outside-of-docker, not plain SSH).
docker compose up -d --no-deps "$SERVICE"

echo "== waiting for '$NAME' to report healthy =="
i=0
while [ "$i" -lt 30 ]; do
  status="$(docker inspect "$NAME" --format '{{.State.Status}} {{.State.Health.Status}}' 2>/dev/null || echo 'absent absent')"
  echo "  [$i] $status"
  case "$status" in
    "running healthy") break ;;
  esac
  i=$((i + 1))
  sleep 4
done
final="$(docker inspect "$NAME" --format '{{.State.Status}} {{.State.Health.Status}} {{.Config.Image}}' 2>/dev/null || echo 'absent absent absent')"
echo "== final: $final =="
case "$final" in
  "running healthy"*) ;;
  *) echo "FAIL: $NAME did not reach running+healthy"; exit 1 ;;
esac
if [ -n "$EXPECTED_IMAGE" ]; then
  case "$final" in
    *"$EXPECTED_IMAGE"*) echo "OK: image matches expected" ;;
    *) echo "FAIL: expected image $EXPECTED_IMAGE, got: $final"; exit 1 ;;
  esac
fi
echo "RECREATE PASS"
