#!/usr/bin/env sh
# Installs BOTH reconciliation jobs
# as host cron entries, same model scripts/install-log-retention-cron.sh
# already uses (this deployment has no APScheduler-in-Flask or other
# in-process scheduler -- host cron + `docker compose exec` is the existing,
# proven pattern, so this reuses it rather than adding a new mechanism).
#
# Idempotent: any existing line for either job (matched by its own command
# substring) is replaced, never duplicated, regardless of how many times or
# how many deploys this runs -- and every OTHER existing crontab line
# (unrelated jobs a human or another tool installed) is left untouched.
#
# Usage: ./scripts/install-reconcile-cron.sh
#   MESFLOW_ROOT (default /opt/mesflow), MESFLOW_APP_SERVICE (default
#   "mesflow" -- the docker compose service name to exec into; MUST match
#   the target's actual compose service, e.g. "mesflow-prodtest-app" for
#   the prodtest target -- see scripts/deploy_lib.sh's target_config()),
#   MESFLOW_EXCEPTION_RECONCILE_CRON (default "*/5 * * * *"),
#   MESFLOW_SHIFT_RECONCILE_CRON (default "* * * * *") are overridable the
#   same way the log-retention installer's MESFLOW_LOG_RETENTION_CRON is.
set -eu

if ! command -v crontab >/dev/null 2>&1; then
  echo "ERROR: 'crontab' is not available on this host -- cannot install the" >&2
  echo "exception_reconciliation / shift_session_reconciliation jobs. Install" >&2
  echo "cron (e.g. 'apt-get install cron') and re-run this script; a deploy" >&2
  echo "must not report PASS while these jobs are unscheduled." >&2
  exit 1
fi

ROOT_DIR="${MESFLOW_ROOT:-/opt/mesflow}"
APP_SERVICE="${MESFLOW_APP_SERVICE:-mesflow}"
EXCEPTION_SCHEDULE="${MESFLOW_EXCEPTION_RECONCILE_CRON:-*/5 * * * *}"
SHIFT_SCHEDULE="${MESFLOW_SHIFT_RECONCILE_CRON:-* * * * *}"
EXCEPTION_LINE="$EXCEPTION_SCHEDULE cd $ROOT_DIR && docker compose exec -T $APP_SERVICE python -m mesflow.cli reconcile-exceptions >> runtime/exception-reconcile.log 2>&1"
SHIFT_LINE="$SHIFT_SCHEDULE cd $ROOT_DIR && docker compose exec -T $APP_SERVICE python -m mesflow.cli reconcile-shift-sessions >> runtime/shift-reconcile.log 2>&1"
(
  crontab -l 2>/dev/null | grep -v 'reconcile-exceptions' | grep -v 'reconcile-shift-sessions' || true
  echo "$EXCEPTION_LINE"
  echo "$SHIFT_LINE"
) | crontab -
echo "Installed: $EXCEPTION_LINE"
echo "Installed: $SHIFT_LINE"
echo ""
echo "NOTE (Phase 15 rollout safety): MESFLOW_SHIFT_AUTO_CLOSE_ENABLED defaults"
echo "to 0 and MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN defaults to 1 -- installing this"
echo "cron alone does NOT start auto-closing real sessions. Run"
echo "'mesflow audit-sessions' first, inspect a dry-run cycle's log output,"
echo "THEN set MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1 and"
echo "MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=0 in the target environment's .env."
