#!/usr/bin/env sh
# Codex audit: proves the required maintenance jobs are ACTUALLY
# present in the current user's crontab -- not just that the installer
# scripts exist in the source tree. A successful application deploy must
# not be able to leave a target in the state "code present, CLI present,
# cron missing, scheduler never runs".
#
# Run standalone on any already-deployed host to audit it, or from
# scripts/deploy.sh right after install-reconcile-cron.sh /
# install-log-retention-cron.sh -- deploy.sh treats a non-zero exit here as
# a deploy-blocking failure, same as a failed health check.
#
# Usage: ./scripts/verify-scheduler-cron.sh
#   MESFLOW_LOG_RETENTION_HOST_CRON=0 skips the log_retention check for a
#   target that deliberately doesn't manage it via host cron.
set -eu

if ! command -v crontab >/dev/null 2>&1; then
  echo "MISSING: 'crontab' command not available on this host -- no scheduled jobs can be installed" >&2
  exit 1
fi

CRONTAB_OUT="$(crontab -l 2>/dev/null || true)"
MISSING=0

check() {
  name="$1"; pattern="$2"
  if printf '%s\n' "$CRONTAB_OUT" | grep -qF -- "$pattern"; then
    echo "OK: $name cron entry present"
  else
    echo "MISSING: $name cron entry NOT found in crontab" >&2
    MISSING=1
  fi
}

check "exception_reconciliation" "reconcile-exceptions"
check "shift_session_reconciliation" "reconcile-shift-sessions"
if [ "${MESFLOW_LOG_RETENTION_HOST_CRON:-1}" = "1" ]; then
  check "log_retention" "cleanup-logs.sh"
fi

[ "$MISSING" -eq 0 ]
