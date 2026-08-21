#!/usr/bin/env bash
# Produce release-local QA evidence for Deploy Agent / ProjectFlow gates.
# Runs only against the isolated ProjectFlow local sandbox. It never touches
# the live deployment-target compose stack or production services.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION.txt)"
ARTIFACT_ROOT="$(cd "$ROOT/.." && pwd)/artifacts"
EVIDENCE_DIR="${MESFLOW_QA_EVIDENCE_DIR:-$ARTIFACT_ROOT/qa/$VERSION/release-local}"
LOG_DIR="$EVIDENCE_DIR/logs"
JSON_FILE="$EVIDENCE_DIR/release-local-qa.json"
SUMMARY_FILE="$EVIDENCE_DIR/SUMMARY.txt"
KEEP_RUNNING=0

usage(){
  cat <<USAGE
Usage: $0 [--keep-running] [--evidence-dir PATH]

Run release-local QA in the isolated ProjectFlow Docker sandbox and write
machine-readable evidence for the release gate.

  --keep-running       leave the isolated local sandbox running after QA
  --evidence-dir PATH  override evidence output directory
USAGE
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-running) KEEP_RUNNING=1; shift ;;
    --evidence-dir) EVIDENCE_DIR="${2:?--evidence-dir requires PATH}"; LOG_DIR="$EVIDENCE_DIR/logs"; JSON_FILE="$EVIDENCE_DIR/release-local-qa.json"; SUMMARY_FILE="$EVIDENCE_DIR/SUMMARY.txt"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OVERALL="PASS"
FAILED_STEP=""
CURRENT_STEP=""

run_step(){
  local name="$1"; shift
  CURRENT_STEP="$name"
  echo "===== QA STEP: $name ====="
  if "$@" > >(tee "$LOG_DIR/$name.log") 2> >(tee "$LOG_DIR/$name.log" >&2); then
    printf 'PASS\n' > "$EVIDENCE_DIR/$name.status"
  else
    local rc=$?
    printf 'FAIL rc=%s\n' "$rc" > "$EVIDENCE_DIR/$name.status"
    OVERALL="FAIL"
    FAILED_STEP="$name"
    return "$rc"
  fi
}

cleanup(){
  local rc=$?
  if [[ "$KEEP_RUNNING" -eq 0 ]] && command -v docker >/dev/null 2>&1; then
    ./scripts/projectflow/stop-local.sh >"$LOG_DIR/local-stop.log" 2>&1 || true
  fi
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export VERSION STARTED_AT FINISHED_AT OVERALL FAILED_STEP EVIDENCE_DIR JSON_FILE
  python3 - <<'PY'
import hashlib, json, os, pathlib
root = pathlib.Path(os.environ['EVIDENCE_DIR'])
steps = {}
for p in sorted(root.glob('*.status')):
    text = p.read_text(encoding='utf-8').strip()
    steps[p.stem] = {'status': 'PASS' if text.startswith('PASS') else 'FAIL', 'detail': text}
meta_path = pathlib.Path('../artifacts/latest/mesflow-app.json')
artifact = None
if meta_path.exists():
    try: artifact = json.loads(meta_path.read_text(encoding='utf-8'))
    except Exception: artifact = None
logs = {}
for p in sorted((root/'logs').glob('*.log')):
    logs[p.name] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
out = {
    'schema': 'mesflow.release-local-qa.v1',
    'project': 'mesflow-app',
    'version': os.environ['VERSION'],
    'environment': 'local-sandbox',
    'overall': os.environ['OVERALL'],
    'failed_step': os.environ.get('FAILED_STEP') or None,
    'started_at': os.environ['STARTED_AT'],
    'finished_at': os.environ['FINISHED_AT'],
    'artifact': artifact,
    'steps': steps,
    'logs': logs,
}
path = pathlib.Path(os.environ['JSON_FILE'])
path.write_text(json.dumps(out, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
PY
  {
    echo "PROJECT=mesflow-app"
    echo "VERSION=$VERSION"
    echo "ENV=release-local"
    echo "QA_STATUS=$OVERALL"
    echo "FAILED_STEP=${FAILED_STEP:-none}"
    echo "EVIDENCE_JSON=$JSON_FILE"
  } > "$SUMMARY_FILE"
  echo
  cat "$SUMMARY_FILE"
  exit "$rc"
}
trap cleanup EXIT
trap 'OVERALL=FAIL; FAILED_STEP="${CURRENT_STEP:-unexpected}"' ERR

run_step version-verify bash ./scripts/check-version-sync.sh
run_step preflight ./scripts/projectflow/preflight.sh
run_step build ./scripts/projectflow/build.sh
run_step test ./scripts/projectflow/test.sh
run_step deploy-local ./scripts/projectflow/deploy-local.sh
run_step smoke ./scripts/projectflow/smoke.sh
run_step status ./scripts/projectflow/status-local.sh

CURRENT_STEP=""
OVERALL="PASS"
