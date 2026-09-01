#!/usr/bin/env bash
# Bump the MESFlow application version consistently across every declared
# location (see AGENTS.md "MESFlow version rules"):
#   - VERSION.txt (the single source of truth)
#   - release.json ("version")
#   - compose.yml (MESFLOW_IMAGE default tag)
# app/mesflow/__init__.py is NOT written here -- it reads VERSION.txt at
# import time (see its own docstring), so writing VERSION.txt above is
# sufficient; this script only verifies that dynamic-read mechanism is
# still intact.
#
# This ONLY edits source text. It never builds, tags, or pushes a Docker
# image -- run scripts/build-release.sh separately, when ready, to build.
#
# Usage:
#   scripts/bump-version.sh                # increment the last segment (X.Y.Z.W -> X.Y.Z.(W+1))
#   scripts/bump-version.sh 65.8.44.70      # bump to an explicit version
#   scripts/bump-version.sh --to 65.8.44.70 # same, explicit flag form
#   scripts/bump-version.sh --if-released   # idempotent "prepare" mode (see below)
#   scripts/bump-version.sh --no-wait ...   # fail fast (VERSION_PREPARE_BUSY) instead
#                                            # of blocking if another invocation holds
#                                            # the lock; may appear anywhere in argv
#
# --if-released (idempotent, safe to run on every commit / CI trigger):
#   - If the version currently in VERSION.txt already has a frozen release
#     (artifacts/releases/<version>/release.json exists -- see RULE 5 /
#     build-release.sh), that version can never be reused, so this bumps
#     forward to the next unreleased X.Y.Z.W and synchronizes every
#     declaration to it.
#   - If the current version has NOT been released yet, no bump happens --
#     it only re-synchronizes app/mesflow/__init__.py, release.json and
#     compose.yml onto whatever VERSION.txt already says (self-heals drift
#     from a manual/partial edit) and verifies the result.
#   - Either way it never touches a frozen artifacts/releases/* directory --
#     those are read-only history, not an input to this script.
#   - Running it twice in a row with no other changes is a no-op the second
#     time: after the first run the current version is never frozen (this
#     script doesn't build), so it only re-verifies.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
die(){ echo "ERROR: $*" >&2; exit 1; }

# --- Concurrency guard ------------------------------------------------
# Two concurrent invocations (e.g. two CI triggers racing on --if-released)
# must never both read the same "current" version and each independently
# decide to bump -- serialize the whole read-current/decide/write critical
# section below with a flock on .bump-version.lock. --no-wait fails fast
# (VERSION_PREPARE_BUSY) instead of blocking, for callers that would rather
# report busy than stall.
NO_WAIT=0
args=()
for a in "$@"; do
  if [[ "$a" == "--no-wait" ]]; then NO_WAIT=1; else args+=("$a"); fi
done
set -- "${args[@]}"

exec {LOCK_FD}>"$ROOT/.bump-version.lock"
if [[ "$NO_WAIT" -eq 1 ]]; then
  flock -n "$LOCK_FD" || die "VERSION_PREPARE_BUSY: another bump-version.sh invocation holds the lock ($ROOT/.bump-version.lock)"
else
  flock "$LOCK_FD"
fi

[[ -f VERSION.txt ]] || die "VERSION.txt not found in $ROOT"
current="$(tr -d '[:space:]' < VERSION.txt)"
[[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID: current VERSION.txt is not X.Y.Z.W: '$current'"

is_frozen(){ [[ -f "$ROOT/../artifacts/releases/$1/release.json" ]]; }
next_patch(){ python3 -c "print('.'.join('$1'.split('.')[:3] + [str(int('$1'.split('.')[3]) + 1)]))"; }

# Write $1 into every declared location and verify it actually landed
# everywhere -- fail loud rather than leaving a partially-synced,
# inconsistent source tree. Uses a generic X.Y.Z.W pattern (not the old
# value) so it can heal drift of any size, not just a single bump.
sync_and_verify(){
  local target="$1" fail=0
  for f in VERSION.txt app/mesflow/__init__.py release.json compose.yml; do  # __init__.py existence only, not written
    [[ -f "$f" ]] || die "Expected file missing: $f"
  done

  printf '%s' "$target" > VERSION.txt
  # app/mesflow/__init__.py deliberately does NOT embed the version as a
  # literal any more -- it reads VERSION.txt at import time (see its own
  # docstring: bumping used to silently do nothing because __version__ was
  # a separate hardcoded string here). This script must not re-introduce
  # that duplication; the only thing to verify is that the dynamic-read
  # mechanism itself is still intact, which is what actually makes the
  # VERSION.txt write above take effect at runtime.
  sed -i -E "s/\"version\": \"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\"/\"version\": \"${target}\"/" release.json
  sed -i -E "s/mesflow-app:[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/mesflow-app:${target}/" compose.yml

  [[ "$(tr -d '[:space:]' < VERSION.txt)" == "$target" ]] || { echo "VERIFY_FAILED: VERSION.txt" >&2; fail=1; }
  grep -qF "_VERSION_FILE" app/mesflow/__init__.py || { echo "VERIFY_FAILED: app/mesflow/__init__.py (dynamic VERSION.txt read mechanism missing)" >&2; fail=1; }
  grep -qF "\"version\": \"${target}\"" release.json || { echo "VERIFY_FAILED: release.json" >&2; fail=1; }
  grep -qF "mesflow-app:${target}" compose.yml || { echo "VERIFY_FAILED: compose.yml" >&2; fail=1; }
  [[ "$fail" -eq 0 ]] || die "One or more version declarations failed to update; inspect working tree before proceeding."
}

if [[ "${1:-}" == "--if-released" ]]; then
  if is_frozen "$current"; then
    target="$(next_patch "$current")"
    # Paranoia: skip past any run of versions that somehow got frozen
    # already (e.g. a concurrent build), never reusing a frozen number.
    while is_frozen "$target"; do target="$(next_patch "$target")"; done
    sync_and_verify "$target"
    echo "VERSION_PREPARE: $current is frozen (already released) -> bumped to $target"
    echo "Files updated: VERSION.txt, release.json, compose.yml (app/mesflow/__init__.py reads VERSION.txt directly, verified intact)"
  else
    sync_and_verify "$current"
    echo "VERSION_PREPARE: $current not yet released -> no bump, declarations synchronized"
  fi
  exit 0
fi

if [[ "${1:-}" == "--to" ]]; then
  target="${2:-}"
else
  target="${1:-}"
fi
if [[ -z "$target" ]]; then
  target="$(next_patch "$current")"
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
is_frozen "$target" && die "VERSION_ALREADY_RELEASED: artifacts/releases/$target/release.json already exists (frozen). Choose a different target version."

sync_and_verify "$target"

echo "VERSION BUMP PASS"
echo "Old version: $current"
echo "New version: $target"
echo "Files updated: VERSION.txt, release.json, compose.yml (app/mesflow/__init__.py reads VERSION.txt directly, verified intact)"
echo "NOTE: no build was run. Build with scripts/build-release.sh when ready."
