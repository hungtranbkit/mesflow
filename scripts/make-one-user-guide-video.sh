#!/usr/bin/env bash
set -Eeuo pipefail
MODULE="${1:-overview}"
BASE_URL="${2:-http://127.0.0.1:8080}"
export MESFLOW_VIDEO_OUTPUT="${MESFLOW_VIDEO_OUTPUT:-$HOME/mesflow-user-guide}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Reuse the same detailed spec but run only one module directly from a writable temp copy.
WS="$HOME/.mesflow-video-one"
rm -rf "$WS"; mkdir -p "$WS/tests/e2e" "$MESFLOW_VIDEO_OUTPUT"
cp "$ROOT/package.json" "$WS/"
[[ -f "$ROOT/package-lock.json" ]] && cp "$ROOT/package-lock.json" "$WS/" || true
cp "$ROOT/playwright.tutorial-detailed.config.js" "$WS/"
cp "$ROOT/tests/e2e/tutorial-detailed.spec.js" "$WS/tests/e2e/"
mkdir -p "$WS/tutorial"
cp "$ROOT/tutorial/tutorial.config.json" "$ROOT/tutorial/terminology.json" "$WS/tutorial/"
cd "$WS"
npm install >/dev/null
npx playwright install chromium >/dev/null
MESFLOW_BASE_URL="$BASE_URL" MESFLOW_TUTORIAL_MODULE="$MODULE" \
MESFLOW_TUTORIAL_WAIT_MS="${MESFLOW_TUTORIAL_WAIT_MS:-6000}" \
MESFLOW_TUTORIAL_STEP_WAIT_MS="${MESFLOW_TUTORIAL_STEP_WAIT_MS:-7500}" \
MESFLOW_TUTORIAL_LONG_WAIT_MS="${MESFLOW_TUTORIAL_LONG_WAIT_MS:-10000}" \
  npx playwright test tests/e2e/tutorial-detailed.spec.js --config=playwright.tutorial-detailed.config.js
video="$(find test-results/tutorial-detailed -type f -name '*.webm' -printf '%T@ %p\n'|sort -nr|head -1|cut -d' ' -f2-)"
cp "$video" "$MESFLOW_VIDEO_OUTPUT/${MODULE}.webm"
echo "$MESFLOW_VIDEO_OUTPUT/${MODULE}.webm"
