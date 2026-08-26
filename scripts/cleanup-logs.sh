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
    # log_retention is still seeded in scheduled_job_health
    # (migration 0033) but nothing ever reported to it -- same false-green
    # NEVER_RUN gap as exception_reconciliation had. scheduled_job_run() is
    # ungated (see its own docstring) so this is truthful in every env this
    # cron entry actually runs in.
    from mesflow.core.scheduled_job import scheduled_job_run
    with scheduled_job_run('log_retention'):
        result=run(dry_run=False)
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
else:
    raise SystemExit('Usage: cleanup-logs.sh [preview|dry-run|run]')
PY
