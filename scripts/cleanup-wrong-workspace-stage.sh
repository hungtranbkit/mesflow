#!/usr/bin/env bash
# Safely clean MESFlow release files that were mistakenly staged into the
# umbrella workspace (/home/dell/workspace/mesflow) instead of the real app
# root (/home/dell/workspace/mesflow/mesflow).
#
# Safety model:
# - never recursively deletes the workspace;
# - never touches protected sibling projects;
# - only acts on files whose current SHA256 exactly matches a known bad-stage
#   release manifest (71.0.0.35/.37/.38);
# - tracked files are restored from Git HEAD;
# - untracked matching files are backed up, then removed;
# - every affected file is backed up before mutation.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PARENT="${HOME:-/home/dell}/workspace/mesflow"
PARENT="${MESFLOW_UMBRELLA_ROOT:-$DEFAULT_PARENT}"
APPLY=0

usage(){
  cat <<EOF
Usage: $0 [--workspace-parent PATH] [--apply]

Default is DRY RUN. Use --apply after reviewing the planned changes.
Expected umbrella workspace: ~/workspace/mesflow
Expected MESFlow app root:   ~/workspace/mesflow/mesflow
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace-parent) PARENT="${2:?missing path}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PARENT="$(cd "$PARENT" && pwd -P)" || { echo "ERROR: workspace parent not found" >&2; exit 1; }
APP_ROOT="$PARENT/mesflow"

# Hard boundary checks. These deliberately require the known umbrella layout.
[[ "$(basename "$PARENT")" == "mesflow" ]] || { echo "ERROR: unsafe parent: $PARENT" >&2; exit 1; }
[[ -d "$PARENT/.git" ]] || { echo "ERROR: $PARENT is not the expected Git workspace (.git missing)" >&2; exit 1; }
[[ -d "$APP_ROOT" ]] || { echo "ERROR: real MESFlow app root missing: $APP_ROOT" >&2; exit 1; }
[[ -d "$PARENT/deploy-agent" ]] || { echo "ERROR: deploy-agent sibling missing; refusing cleanup" >&2; exit 1; }

MANIFESTS=(
  "$SCRIPT_DIR/manifests/wrong-stage-71.0.0.35.sha256"
  "$SCRIPT_DIR/manifests/wrong-stage-71.0.0.37.sha256"
  "$SCRIPT_DIR/manifests/wrong-stage-71.0.0.38.sha256"
)
for m in "${MANIFESTS[@]}"; do [[ -f "$m" ]] || { echo "ERROR: missing manifest $m" >&2; exit 1; }; done

# Plan matching files with Python in one process; this keeps SHA and Git-index
# checks fast even across hundreds of release files.
stamp="$(date +%Y%m%d-%H%M%S)"
BACKUP="${PARENT%/}-wrong-stage-backup-$stamp.tar.gz"
PLAN="$(mktemp)"
ALL_LIST="$(mktemp)"
RESTORE_LIST="$(mktemp)"
REMOVE_LIST="$(mktemp)"
trap 'rm -f "$PLAN" "$ALL_LIST" "$RESTORE_LIST" "$REMOVE_LIST"' EXIT

python3 - "$PARENT" "$PLAN" "${MANIFESTS[@]}" <<'PYPLAN'
import hashlib
import pathlib
import subprocess
import sys

parent = pathlib.Path(sys.argv[1])
plan = pathlib.Path(sys.argv[2])
manifests = [pathlib.Path(x) for x in sys.argv[3:]]

protected_prefixes = (
    'mesflow/', 'deploy-agent/', 'qa-center/', 'esp-kiosk/', 'mesflow-web/',
    'runtime/', 'runtime-projectflow-local/', 'artifacts/', '.git/', '.projectflow/'
)
protected_exact = {'.env'}

known = {}
for manifest in manifests:
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split('  ', 1)
        known.setdefault(rel, set()).add(digest)

tracked_raw = subprocess.check_output(['git', '-C', str(parent), 'ls-files', '-z'])
tracked = {x.decode() for x in tracked_raw.split(b'\0') if x}

def protected(rel):
    return rel in protected_exact or any(rel.startswith(p) for p in protected_prefixes)

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

rows = []
for rel, hashes in known.items():
    if protected(rel):
        continue
    path = parent / rel
    if not path.is_file() or path.is_symlink():
        continue
    if sha256(path) not in hashes:
        continue
    rows.append(('RESTORE' if rel in tracked else 'REMOVE', rel))

rows = sorted(set(rows))
plan.write_text(''.join(f'{action}\t{rel}\n' for action, rel in rows))
PYPLAN

sort -u -o "$PLAN" "$PLAN"
count="$(wc -l < "$PLAN" | tr -d ' ')"
echo "MESFlow wrong-stage cleanup"
echo "Workspace parent : $PARENT"
echo "Real app root    : $APP_ROOT"
echo "Matched changes  : $count"
echo "Mode             : $([[ "$APPLY" -eq 1 ]] && echo APPLY || echo DRY_RUN)"

if [[ "$count" == "0" ]]; then
  echo "Nothing safe to clean. No files changed."
  exit 0
fi

cat "$PLAN"

if [[ "$APPLY" -ne 1 ]]; then
  echo
  echo "Dry run only. Re-run with --apply to execute the exact plan above."
  exit 0
fi

# Back up every affected file in one archive before mutation.
while IFS=$'\t' read -r action rel; do
  printf '%s\0' "$rel" >> "$ALL_LIST"
  case "$action" in
    RESTORE) printf '%s\0' "$rel" >> "$RESTORE_LIST" ;;
    REMOVE) printf '%s\0' "$rel" >> "$REMOVE_LIST" ;;
    *) echo "ERROR: bad action $action" >&2; exit 1 ;;
  esac
done < "$PLAN"

tar -czf "$BACKUP" --null -T "$ALL_LIST"

# Apply in batches. xargs keeps argv sizes safe even for large manifests.
if [[ -s "$RESTORE_LIST" ]]; then
  xargs -0 -r git restore --worktree -- < "$RESTORE_LIST"
fi
if [[ -s "$REMOVE_LIST" ]]; then
  xargs -0 -r rm -f -- < "$REMOVE_LIST"
fi

# Remove only directories made empty by file cleanup; never recurse.
for d in app scripts tests reports docs gateway nginx tutorial codex_batch .agents .codex .github .impeccable; do
  [[ -d "$PARENT/$d" ]] || continue
  find "$PARENT/$d" -depth -type d -empty -delete 2>/dev/null || true
done

echo "Cleanup complete."
echo "Backup: $BACKUP"
echo "Protected sibling projects were not touched."
echo "Next: stage the corrected release into $APP_ROOT using its install.sh."
