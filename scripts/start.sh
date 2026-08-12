#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || bash scripts/prepare-env.sh
bash scripts/deploy.sh
