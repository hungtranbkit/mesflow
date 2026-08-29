#!/usr/bin/env bash
# Usage:
#   build-release.sh                # build VERSION.txt exactly as it is now (default, unchanged)
#   build-release.sh --bump         # scripts/bump-version.sh (+1 last segment) first, then build
#   build-release.sh --bump X.Y.Z.W # bump to an explicit version first, then build
#
# --bump is opt-in, not the default: this script is also what Deploy
# Agent's own "Build Release" button runs unattended on every click
# (POST /api/release-manager/build), and that must keep building whatever
# VERSION.txt already declares -- auto-bumping there would silently burn a
# version number on every retry/click. Bumping is a deliberate human
# decision; --bump only exists so a manual "bump then build" doesn't need
# two separate commands (real friction: previously the only way to do
# both was to run scripts/bump-version.sh by hand first).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
die(){ echo "ERROR: $*" >&2; exit 1; }
command -v docker >/dev/null || die "DOCKER_NOT_FOUND"

BUMP=0
BUMP_TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump)
      BUMP=1; shift
      if [[ $# -gt 0 && "$1" != --* ]]; then BUMP_TARGET="$1"; shift; fi
      ;;
    *) die "Unknown argument: $1 (usage: build-release.sh [--bump [VERSION]])" ;;
  esac
done
if [[ "$BUMP" -eq 1 ]]; then
  echo "Bumping version first (scripts/bump-version.sh)..."
  bash "$ROOT/scripts/bump-version.sh" ${BUMP_TARGET:+"$BUMP_TARGET"}
fi

version="$(tr -d '[:space:]' < VERSION.txt)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID"
image_repo="${MESFLOW_IMAGE_REPOSITORY:-mesflow-app}"
image="${image_repo}:$version"
dist="$ROOT/../artifacts/releases/$version"

# --- immutable release guard --------------------------------------------
# A version may be built only once. Never overwrite a frozen release.json /
# checksums.txt / deploy ZIP / image-info.json — that is exactly how
# 65.8.44.65 ended up with two different image digests under one version
# number (a second build silently overwrote the first's release record and
# moved the Docker tag). Any rebuild must use a new VERSION.txt.
if [[ -f "$dist/release.json" ]]; then
  die "VERSION_ALREADY_RELEASED: artifacts/releases/$version/release.json already exists (frozen). A version may be built only once. Bump VERSION.txt to a new version (e.g. the next patch) and rebuild."
fi
mkdir -p "$dist"

# Build into a disposable local tag first. Only promote it to the canonical
# version tag ($image) after confirming that tag isn't already in use by a
# *different* image — moving an existing tag to new bytes under the same
# version number is exactly the contamination bug this guards against.
build_tag="${image}__building_$$"
cleanup_build_tag(){ docker rmi "$build_tag" >/dev/null 2>&1 || true; }
trap cleanup_build_tag EXIT
docker build -t "$build_tag" .
new_id="$(docker image inspect "$build_tag" --format '{{.Id}}')"
[[ "$new_id" == sha256:* ]] || die "IMAGE_ID_UNAVAILABLE"
if docker image inspect "$image" >/dev/null 2>&1; then
  existing_id="$(docker image inspect "$image" --format '{{.Id}}')"
  if [[ "$existing_id" != "$new_id" ]]; then
    die "IMAGE_TAG_CONTAMINATED: $image already exists (id=$existing_id) and differs from the image just built from current source (id=$new_id). A version may be built only once. Bump VERSION.txt to a new version and rebuild — never retag over an existing version."
  fi
  echo "NOTE: $image already exists and matches the freshly built image exactly (idempotent rebuild, no source change) — proceeding."
fi
docker tag "$build_tag" "$image"
image_id="$new_id"
digest="$image_id"
# -c safe.directory: the workspace is frequently bind-mounted into a
# container (e.g. the Dockerized Deploy Agent) running as a different UID
# than the directory owner, which trips git's "dubious ownership"
# protection and makes rev-parse fail silently into "unknown" here. Scope
# the exception to this one invocation instead of relying on a persistent
# global gitconfig in the image.
source_commit="$(git -c safe.directory='*' rev-parse HEAD 2>/dev/null || echo unknown)"

# Resolve the true Alembic head by walking the revision/down_revision graph
# under app/migrations/versions — NOT a filename-sort heuristic, and NOT the
# path pattern '*alembic*' (migrations live under app/migrations/versions,
# which does not match that pattern; the old heuristic silently produced an
# empty schema_revision on every build).
schema_revision="$(python3 - "$ROOT/app/migrations/versions" <<'PY'
import ast, pathlib, sys
versions_dir = pathlib.Path(sys.argv[1])
revisions = {}
down_of = set()
for f in sorted(versions_dir.glob("*.py")):
    if f.name == "__init__.py":
        continue
    tree = ast.parse(f.read_text(encoding="utf-8"))
    rev = down = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == "revision" and isinstance(node.value, ast.Constant):
                rev = node.value.value
            elif name == "down_revision":
                if isinstance(node.value, ast.Constant):
                    down = node.value.value
                elif isinstance(node.value, (ast.Tuple, ast.List)):
                    down = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    if rev:
        revisions[rev] = f.name
        if down:
            down_of.update(down if isinstance(down, list) else [down])
heads = [r for r in revisions if r not in down_of]
if len(heads) == 1:
    print(heads[0])
elif len(heads) > 1:
    print("MULTIPLE_HEADS:" + ",".join(sorted(heads)), file=sys.stderr)
    sys.exit(1)
else:
    print("unknown")
PY
)" || die "SCHEMA_REVISION_RESOLUTION_FAILED (multiple Alembic heads or unreadable migrations — see stderr above)"
[[ -n "$schema_revision" ]] || schema_revision="unknown"

built_at="$(date -Is)"
tmp="$(mktemp -d)"
cleanup_all(){ cleanup_build_tag; rm -rf "$tmp"; }
trap cleanup_all EXIT
root="$tmp/mesflow-release"; mkdir -p "$root"
cp VERSION.txt "$root/VERSION.txt"
cp compose.yml "$root/compose.yml"
docker save "$image" -o "$root/MESFlow_${version}.tar"
cat > "$root/release.json" <<JSON
{"type":"mesflow-image-release","version":"$version","image":"$image","image_digest":"$digest","image_id":"$image_id","source_commit":"$source_commit","built_at":"$built_at","schema_revision":"$schema_revision","requires_migration":false,"distribution":"bundle","bundle":"MESFlow_${version}.tar"}
JSON
cat > "$root/PROMOTION.json" <<JSON
{"version":"$version","image_digest":"$digest","source_commit":"$source_commit","local":{"status":"NOT_DEPLOYED"},"production_test":{"status":"NOT_DEPLOYED"},"production":{"status":"NOT_DEPLOYED"}}
JSON
(cd "$root" && sha256sum MESFlow_${version}.tar compose.yml release.json VERSION.txt > checksums.txt)
cp "$root/release.json" "$dist/release.json"; cp "$root/PROMOTION.json" "$dist/PROMOTION.json"; cp "$root/checksums.txt" "$dist/checksums.txt"
package="$dist/MESFlow_${version}.deploy.zip"
if command -v zip >/dev/null 2>&1; then
  (cd "$tmp" && zip -qr "$package" mesflow-release)
else
  python3 - "$tmp" "$package" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for path in (root / "mesflow-release").rglob("*"):
        if path.is_file():
            z.write(path, path.relative_to(root).as_posix())
PY
fi
sha256sum "$dist/MESFlow_${version}.deploy.zip" > "$dist/MESFlow_${version}.deploy.zip.sha256"
package_filename="MESFlow_${version}.deploy.zip"
package_sha256="$(awk '{print $1}' "$dist/${package_filename}.sha256")"

# --- ProjectFlow-facing artifact metadata contract -----------------------
# This is the ONE machine-readable metadata file external tooling (right
# now: ProjectFlow's DeploymentService, per PROJECT.yaml's
# artifacts.metadata) reads after a build. Two copies, same schema, same
# values, written together so they can never drift apart:
#   - artifacts/releases/<version>/image-info.json -- immutable, frozen by
#     the same VERSION_ALREADY_RELEASED guard as the rest of this release
#     (the historical evidence for this exact version, forever).
#   - artifacts/latest/mesflow-app.json -- a "latest" pointer, but a REAL
#     one: deliberately (re)written by this build, never a file some other
#     process was expected to have created ahead of time. A caller that
#     needs the artifact for one specific, already-known commit should
#     still cross-check metadata.source_commit against what it expected
#     (this file can be clobbered by a later, unrelated build finishing
#     after the caller reads it) rather than trust "latest" blindly.
metadata_json="$(printf '{"image":"%s","digest":"%s","source_commit":"%s","version":"%s","image_name":"%s","image_tag":"%s","image_digest":"%s","package_filename":"%s","package_sha256":"%s","built_at":"%s"}\n' \
  "$image" "$digest" "$source_commit" "$version" "$image_repo" "$version" "$digest" "$package_filename" "$package_sha256" "$built_at")"
printf '%s' "$metadata_json" > "$dist/image-info.json"
mkdir -p "$ROOT/../artifacts/latest"
printf '%s' "$metadata_json" > "$ROOT/../artifacts/latest/mesflow-app.json"
cat > "$dist/BUILD_REPORT.md" <<EOF
# MESFlow image build

- Version: $version
- Image: $image
- Digest: $digest
- Source commit: $source_commit
- Schema revision (Alembic head): $schema_revision
- Distribution: bundle
- Server-side source build: disabled for this package
EOF
echo "IMAGE RELEASE PASS"; echo "Version: $version"; echo "Image: $image"; echo "Digest: $digest"; echo "Schema: $schema_revision"; echo "Package: $dist/MESFlow_${version}.deploy.zip"
