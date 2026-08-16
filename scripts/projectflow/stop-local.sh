#!/usr/bin/env bash
# ProjectFlow contract: local_stop. Stops/removes only the isolated sandbox
# containers (mesflow-projectflow-local-*). Never runs against the real
# deployment-target compose project. Data under runtime-projectflow-local/
# is a bind mount and survives (no `-v`), so a subsequent deploy-local.sh
# resumes with the same local data -- idempotent restart, not a wipe.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

echo "===== MESFlow App stop-local (sandbox) ====="
pf_compose down --remove-orphans
echo "STOP LOCAL PASS"
