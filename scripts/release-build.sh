#!/usr/bin/env bash
# Build once on DEV, smoke-test against an ephemeral throwaway Postgres,
# push to the registry, capture the immutable digest, write a release
# manifest. Never run this on prodtest/production -- they only pull.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/deploy_lib.sh

VERSION="$(cat VERSION.txt)"
COMMIT="$(git rev-parse --short=12 HEAD)"
DIRTY_COUNT="$(git status --short | wc -l | tr -d ' ')"
DIRTY=false
if [[ "$DIRTY_COUNT" != "0" ]]; then
  DIRTY=true
  if [[ "${ALLOW_DIRTY_BUILD:-}" != "1" ]]; then
    echo "ABORT: working tree has $DIRTY_COUNT uncommitted change(s). Commit first -- a durable release must be reproducible from committed source." >&2
    echo "  git status --short   # see what's dirty" >&2
    echo "Set ALLOW_DIRTY_BUILD=1 to override for a throwaway local iteration build (never do this for a release you intend to keep/promote)." >&2
    exit 1
  fi
  echo "WARNING: ALLOW_DIRTY_BUILD=1 -- building from a dirty working tree ($DIRTY_COUNT change(s)). This is NOT a durable release." >&2
  COMMIT="${COMMIT}-dirty"
fi

IMAGE_TAG="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
echo "== Building ${IMAGE_TAG} (commit ${COMMIT}) =="
docker build --build-arg GIT_COMMIT="${COMMIT}" -t "${IMAGE_TAG}" .

echo "== Smoke test: ephemeral Postgres + migrate + health =="
TEST_NET="mesflow-release-smoke-$$"
docker network create "$TEST_NET" >/dev/null
TEST_PW="smoke-$$-$(date +%s)"
cleanup() {
  docker rm -f release-smoke-db release-smoke-app >/dev/null 2>&1 || true
  docker network rm "$TEST_NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --name release-smoke-db --network "$TEST_NET" \
  -e POSTGRES_DB=mesflow_smoke -e POSTGRES_USER=mesflow -e POSTGRES_PASSWORD="$TEST_PW" \
  postgres:17-alpine >/dev/null
echo -n "waiting for smoke DB"
for _ in $(seq 1 30); do
  docker exec release-smoke-db pg_isready -U mesflow -d mesflow_smoke >/dev/null 2>&1 && break
  echo -n "."; sleep 1
done
echo

docker run -d --name release-smoke-app --network "$TEST_NET" \
  -e SERVER_ROLE=RELEASE_SMOKE -e MESFLOW_ENV=production \
  -e DATABASE_URL="postgresql://mesflow:${TEST_PW}@release-smoke-db:5432/mesflow_smoke" \
  -e WORKSHOP_DATABASE_URL="postgresql://mesflow:${TEST_PW}@release-smoke-db:5432/mesflow_smoke" \
  -e MESFLOW_SECRET_KEY="release-smoke-only-$$" \
  -e MESFLOW_ADMIN_PASSWORD="ReleaseSmokeOnly123" \
  "$IMAGE_TAG" >/dev/null

echo -n "waiting for app to become ready"
READY=""
for _ in $(seq 1 60); do
  RESP="$(docker exec release-smoke-app curl -fsS http://127.0.0.1:8080/api/system/ready 2>/dev/null || true)"
  if [[ -n "$RESP" ]]; then READY="$RESP"; break; fi
  echo -n "."; sleep 1
done
echo
if [[ -z "$READY" ]]; then
  echo "SMOKE TEST FAILED: app never became ready. Logs:" >&2
  docker logs release-smoke-app --tail 60 >&2
  exit 1
fi
echo "Smoke response: $READY"
MIGRATION_HEAD="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('migration_head'))" "$READY")"
BUILT_COMMIT="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('commit'))" "$READY")"
if [[ "$BUILT_COMMIT" != "$COMMIT" ]]; then
  echo "SMOKE TEST FAILED: image reports commit '$BUILT_COMMIT', expected '$COMMIT'" >&2
  exit 1
fi

curl -fsS -o /dev/null "http://127.0.0.1:$(docker port release-smoke-app 8080/tcp | cut -d: -f2)/api/kiosk/v2/health" 2>/dev/null \
  || docker exec release-smoke-app curl -fsS -o /dev/null http://127.0.0.1:8080/api/kiosk/v2/health
echo "kiosk v2 health OK"
echo "NOTE: this is a migrate+boot+health smoke test, not the full pytest suite (354 tests, needs a longer-lived Postgres fixture) -- run that separately with your normal test workflow before relying on this for correctness beyond boot/migrate."

echo "== Pushing =="
docker push "$IMAGE_TAG"
DIGEST_REF="$(docker image inspect --format='{{index .RepoDigests 0}}' "$IMAGE_TAG")"
DIGEST="${DIGEST_REF#*@}"

mkdir -p "$RELEASE_DIR"
MANIFEST="$RELEASE_DIR/mesflow-${VERSION}.json"
cat > "$MANIFEST" <<EOF
{
  "version": "${VERSION}",
  "commit": "${COMMIT}",
  "dirty": ${DIRTY},
  "image": "${IMAGE_TAG}",
  "digest": "${DIGEST_REF}",
  "migration_head": "${MIGRATION_HEAD}",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "tests": "smoke-only"
}
EOF

echo
echo "== Release manifest: $MANIFEST =="
cat "$MANIFEST"
echo
echo "Deploy with: ./scripts/deploy.sh prodtest ${VERSION}"
