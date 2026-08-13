#!/usr/bin/env bash
# Bump the MESFlow application version consistently across every declared
# location (see AGENTS.md "MESFlow version rules"):
#   - VERSION.txt
#   - app/mesflow/__init__.py (__version__)
#   - release.json ("version")
#   - compose.yml (MESFLOW_IMAGE default tag)
#
# This ONLY edits source text. It never builds, tags, or pushes a Docker
# image -- run scripts/build-release.sh separately, when ready, to build.
#
# Usage:
#   scripts/bump-version.sh                # increment the last segment (X.Y.Z.W -> X.Y.Z.(W+1))
#   scripts/bump-version.sh 65.8.44.70      # bump to an explicit version
#   scripts/bump-version.sh --to 65.8.44.70 # same, explicit flag form
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
die(){ echo "ERROR: $*" >&2; exit 1; }

[[ -f VERSION.txt ]] || die "VERSION.txt not found in $ROOT"
current="$(tr -d '[:space:]' < VERSION.txt)"
[[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID: current VERSION.txt is not X.Y.Z.W: '$current'"

if [[ "${1:-}" == "--to" ]]; then
  target="${2:-}"
else
  target="${1:-}"
fi
if [[ -z "$target" ]]; then
  target="$(python3 -c "print('.'.join('$current'.split('.')[:3] + [str(int('$current'.split('.')[3]) + 1)]))")"
fi
[[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID: target version is not X.Y.Z.W: '$target'"
[[ "$target" != "$current" ]] || die "VERSION_UNCHANGED: target equals current ($current)"

# Never move backward -- compare component by component, numerically.
python3 -c "
import sys
cur=[int(x) for x in '$current'.split('.')]
tgt=[int(x) for x in '$target'.split('.')]
sys.exit(0 if tgt>cur else 1)
" || die "VERSION_NOT_NEWER: target $target is not greater than current $current"

# Refuse to bump onto a version number that's already frozen -- a version
# number is never reused, matching the immutable-once release guard in
# build-release.sh (see AGENTS.md RULE 5).
frozen="$ROOT/../artifacts/releases/$target/release.json"
[[ ! -f "$frozen" ]] || die "VERSION_ALREADY_RELEASED: artifacts/releases/$target/release.json already exists (frozen). Choose a different target version."

for f in VERSION.txt app/mesflow/__init__.py release.json compose.yml; do
  [[ -f "$f" ]] || die "Expected file missing: $f"
done

printf '%s' "$target" > VERSION.txt
sed -i "s/__version__='${current}'/__version__='${target}'/" app/mesflow/__init__.py
sed -i "s/\"version\": \"${current}\"/\"version\": \"${target}\"/" release.json
sed -i "s/mesflow-app:${current}/mesflow-app:${target}/" compose.yml

# Verify every declaration actually landed on the new version -- fail loud
# rather than leaving a partially-bumped, inconsistent source tree.
fail=0
[[ "$(tr -d '[:space:]' < VERSION.txt)" == "$target" ]] || { echo "VERIFY_FAILED: VERSION.txt" >&2; fail=1; }
grep -qF "__version__='${target}'" app/mesflow/__init__.py || { echo "VERIFY_FAILED: app/mesflow/__init__.py" >&2; fail=1; }
grep -qF "\"version\": \"${target}\"" release.json || { echo "VERIFY_FAILED: release.json" >&2; fail=1; }
grep -qF "mesflow-app:${target}" compose.yml || { echo "VERIFY_FAILED: compose.yml" >&2; fail=1; }
[[ "$fail" -eq 0 ]] || die "One or more version declarations failed to update; inspect working tree before proceeding."

echo "VERSION BUMP PASS"
echo "Old version: $current"
echo "New version: $target"
echo "Files updated: VERSION.txt, app/mesflow/__init__.py, release.json, compose.yml"
echo "NOTE: no build was run. Build with scripts/build-release.sh when ready."
