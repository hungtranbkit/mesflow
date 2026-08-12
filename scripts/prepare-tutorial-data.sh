#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-seed}"

if [[ "$ACTION" == "seed" && "${MESFLOW_TUTORIAL_SEED_DATA:-0}" != "1" ]]; then
  echo "[INFO] Không seed dữ liệu tutorial vì MESFLOW_TUTORIAL_SEED_DATA chưa = 1."
  echo "Dùng trên database đào tạo/test:"
  echo "  MESFLOW_TUTORIAL_SEED_DATA=1 bash scripts/prepare-tutorial-data.sh seed"
  exit 0
fi

args=(docker compose exec -T)
if [[ "${MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION:-0}" == "1" ]]; then
  args+=(-e MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1)
fi
if [[ "$ACTION" == "seed" ]]; then
  echo "[Tutorial] Alembic revision:"
  docker compose exec -T mesflow alembic current || true
fi
args+=(mesflow python -m mesflow.tutorial_data "$ACTION")
"${args[@]}"
