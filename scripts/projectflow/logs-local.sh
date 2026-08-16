#!/usr/bin/env bash
# ProjectFlow contract: logs. Local sandbox only. Supports --tail N
# (default 200). Never touches the real deployment's logs/containers.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh
cd "$PF_ROOT"

tail="200"
if [[ "${1:-}" == "--tail" && -n "${2:-}" ]]; then
  tail="$2"
fi

pf_compose logs --tail "$tail"
