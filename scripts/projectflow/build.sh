#!/usr/bin/env bash
# ProjectFlow contract: build. Thin wrapper -- does NOT reimplement the
# build engine. Delegates to the existing, real Build Once / immutable-once
# release builder (mesflow/scripts/build-release.sh, also reachable via the
# workspace-root wrapper scripts/build-release.sh) and then publishes a
# ProjectFlow-shaped metadata pointer alongside it. Never deploys.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

echo "===== MESFlow App build (delegates to scripts/build-release.sh) ====="
./scripts/build-release.sh

version="$(pf_version)"
release_dir="$PF_ARTIFACTS_DIR/$version"
release_json="$release_dir/release.json"
[[ -f "$release_json" ]] || { echo "ERROR: build-release.sh reported success but $release_json is missing" >&2; exit 1; }

mkdir -p "$PF_LATEST_META_DIR"
python3 - "$release_json" "$release_dir" "$PF_LATEST_META" <<'PY'
import json, sys, pathlib
release = json.load(open(sys.argv[1]))
release_dir = pathlib.Path(sys.argv[2])
zips = sorted(release_dir.glob("*.deploy.zip"))
out = {
    "project": "mesflow-app",
    "version": release.get("version"),
    "commit": release.get("source_commit"),
    "artifact_type": "docker-image",
    "artifact": release.get("image"),
    "image_digest": release.get("image_digest"),
    "schema_revision": release.get("schema_revision"),
    "package": str(zips[0].relative_to(release_dir.parent.parent)) if zips else None,
    "built_at": release.get("built_at"),
}
dest = pathlib.Path(sys.argv[3])
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"WROTE {dest}")
PY

echo "BUILD PASS"
echo "Version: $version"
echo "Metadata: $PF_LATEST_META"
