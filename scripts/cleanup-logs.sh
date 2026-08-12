#!/usr/bin/env sh
set -eu
MODE="${1:-run}"
export PYTHONPATH="${PYTHONPATH:-/app/app}"
python - "$MODE" <<'PY'
import json,sys
from mesflow.core.config import settings
from mesflow.core.log_retention import preview,run
mode=sys.argv[1]
if mode in {'preview','dry-run'}:
    print(json.dumps(run(dry_run=True),ensure_ascii=False,indent=2,default=str))
elif mode=='run':
    if not settings.log_retention_enabled:
        raise SystemExit('MESFLOW_LOG_RETENTION_ENABLED=0; cleanup cancelled')
    print(json.dumps(run(dry_run=False),ensure_ascii=False,indent=2,default=str))
else:
    raise SystemExit('Usage: cleanup-logs.sh [preview|dry-run|run]')
PY
