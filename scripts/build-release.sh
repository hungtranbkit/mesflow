#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
die(){ echo "ERROR: $*" >&2; exit 1; }
command -v docker >/dev/null || die "DOCKER_NOT_FOUND"
version="$(tr -d '[:space:]' < VERSION.txt)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID"
image="${MESFLOW_IMAGE_REPOSITORY:-mesflow-app}:$version"
dist="$ROOT/../artifacts/releases/$version"; mkdir -p "$dist"
docker build -t "$image" .
image_id="$(docker image inspect "$image" --format '{{.Id}}')"; [[ "$image_id" == sha256:* ]] || die "IMAGE_ID_UNAVAILABLE"
digest="$image_id"
source_commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
schema_revision="$(find app -path '*alembic*' -type f -name '*.py' -printf '%f\n' 2>/dev/null | sort | tail -1 || echo unknown)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
root="$tmp/mesflow-release"; mkdir -p "$root"
cp VERSION.txt "$root/VERSION.txt"
cp compose.yml "$root/compose.yml"
docker save "$image" -o "$root/MESFlow_${version}.tar"
cat > "$root/release.json" <<JSON
{"type":"mesflow-image-release","version":"$version","image":"$image","image_digest":"$digest","image_id":"$image_id","source_commit":"$source_commit","built_at":"$(date -Is)","schema_revision":"$schema_revision","requires_migration":false,"distribution":"bundle","bundle":"MESFlow_${version}.tar"}
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
printf '{"image":"%s","digest":"%s","source_commit":"%s","version":"%s"}\n' "$image" "$digest" "$source_commit" "$version" > "$dist/image-info.json"
cat > "$dist/BUILD_REPORT.md" <<EOF
# MESFlow image build

- Version: $version
- Image: $image
- Digest: $digest
- Source commit: $source_commit
- Distribution: bundle
- Server-side source build: disabled for this package
EOF
echo "IMAGE RELEASE PASS"; echo "Version: $version"; echo "Image: $image"; echo "Digest: $digest"; echo "Package: $dist/MESFlow_${version}.deploy.zip"
