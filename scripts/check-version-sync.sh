#!/usr/bin/env bash
# Read-only companion to scripts/bump-version.sh: verifies every legitimate
# MESFlow version declaration agrees with VERSION.txt. Never writes to the
# working tree and never touches artifacts/releases (frozen history).
#
# Declarations checked (see AGENTS.md "MESFlow version rules"):
#   - VERSION.txt              (source of truth)
#   - app/mesflow/__init__.py  (__version__)
#   - release.json             ("version")
#   - compose.yml              (MESFLOW_IMAGE default tag)
#
# Usage:
#   scripts/check-version-sync.sh
#
# Exits 0 and prints PASS when all declarations agree. Exits non-zero with
# a VERSION_DRIFT/VERSION_CONTRACT message per mismatch otherwise -- run
# `scripts/bump-version.sh --if-released` to resynchronize.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
die(){ echo "ERROR: $*" >&2; exit 1; }

[[ -f VERSION.txt ]] || die "VERSION.txt not found in $ROOT"
version="$(tr -d '[:space:]' < VERSION.txt)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION_INVALID: VERSION.txt is not X.Y.Z.W: '$version'"

fail=0
check(){
  local label="$1"; shift
  if ! "$@"; then
    echo "VERSION_DRIFT: $label does not declare $version" >&2
    fail=1
  fi
}

[[ -f app/mesflow/__init__.py ]] || die "Expected file missing: app/mesflow/__init__.py"
[[ -f release.json ]] || die "Expected file missing: release.json"
[[ -f compose.yml ]] || die "Expected file missing: compose.yml"

check "app/mesflow/__init__.py" grep -qF "__version__='${version}'" app/mesflow/__init__.py
check "release.json"           grep -qF "\"version\": \"${version}\"" release.json
check "compose.yml"            grep -qF "mesflow-app:${version}" compose.yml

[[ "$fail" -eq 0 ]] || die "VERSION_CONTRACT: one or more declarations do not match VERSION.txt ($version). Run ./scripts/bump-version.sh --if-released to synchronize (never edit frozen artifacts/releases/*)."

echo "VERSION_VERIFY PASS: all declarations agree on $version"
