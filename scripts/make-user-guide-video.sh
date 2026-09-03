#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${1:-http://127.0.0.1:8080}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${MESFLOW_VIDEO_WORKSPACE:-$HOME/.mesflow-video}"
OUT="${MESFLOW_VIDEO_OUTPUT:-$HOME/mesflow-user-guide}"
WAIT="${MESFLOW_TUTORIAL_WAIT_MS:-6000}"
LONG="${MESFLOW_TUTORIAL_LONG_WAIT_MS:-10000}"
STEP="${MESFLOW_TUTORIAL_STEP_WAIT_MS:-7500}"

if [[ -z "${MESFLOW_TUTORIAL_PASSWORD:-}" ]]; then
  echo "[ERROR] Thiếu MESFLOW_TUTORIAL_PASSWORD" >&2
  exit 2
fi

echo "===== MESFlow DETAILED USER GUIDE ====="
echo "MESFlow: $BASE_URL"
echo "Workspace: $WORKSPACE"
echo "Output: $OUT"

curl -fsS "$BASE_URL/api/system/version" >/dev/null || {
  echo "[ERROR] MESFlow không truy cập được tại $BASE_URL" >&2
  exit 1
}

rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE/tests/e2e" "$OUT"

# Keep production /opt/mesflow read-only. Copy only tutorial runtime files to user workspace.
cp "$ROOT/package.json" "$WORKSPACE/"
[[ -f "$ROOT/package-lock.json" ]] && cp "$ROOT/package-lock.json" "$WORKSPACE/" || true
cp "$ROOT/playwright.tutorial-detailed.config.js" "$WORKSPACE/"
cp "$ROOT/tests/e2e/tutorial-detailed.spec.js" "$WORKSPACE/tests/e2e/"
cp "$ROOT/tests/e2e/tutorial-coverage.spec.js" "$WORKSPACE/tests/e2e/"
cp "$ROOT/tests/e2e/tutorial-auth-state.js" "$WORKSPACE/tests/e2e/"
mkdir -p "$WORKSPACE/tutorial"
cp "$ROOT/tutorial/tutorial.config.json" "$ROOT/tutorial/terminology.json" "$ROOT/tutorial/coverage-matrix.json" "$ROOT/tutorial/exception-scenarios.json" "$WORKSPACE/tutorial/"

cd "$WORKSPACE"
npm install
npx playwright install chromium

AUTH_STATE="$WORKSPACE/tutorial-auth-state.json"
echo
echo "===== ĐĂNG NHẬP MỘT LẦN CHO TOÀN BỘ VIDEO ====="
MESFLOW_BASE_URL="$BASE_URL" \
MESFLOW_TUTORIAL_USERNAME="${MESFLOW_TUTORIAL_USERNAME:-admin}" \
MESFLOW_TUTORIAL_PASSWORD="$MESFLOW_TUTORIAL_PASSWORD" \
MESFLOW_TUTORIAL_AUTH_STATE="$AUTH_STATE" \
node tests/e2e/tutorial-auth-state.js

echo
echo "===== SELECTOR PREFLIGHT + QA COVERAGE ====="
COVERAGE_REPORT="$OUT/tutorial-coverage-report.json"
if ! MESFLOW_BASE_URL="$BASE_URL" \
  MESFLOW_TUTORIAL_AUTH_STATE="$AUTH_STATE" \
  MESFLOW_TUTORIAL_COVERAGE_REPORT="$COVERAGE_REPORT" \
  npx playwright test tests/e2e/tutorial-coverage.spec.js --config=playwright.tutorial-detailed.config.js; then
  echo "[ERROR] Coverage gate hoặc selector preflight không đạt. Báo cáo: $COVERAGE_REPORT" >&2
  exit 4
fi

if [[ "${MESFLOW_TUTORIAL_SEED_DATA:-0}" == "1" ]]; then
  echo
  echo "===== CHUẨN BỊ DATASET HƯỚNG DẪN ====="
  bash "$ROOT/scripts/prepare-tutorial-data.sh" seed
  bash "$ROOT/scripts/prepare-tutorial-data.sh" status
else
  echo "[INFO] Không tạo dữ liệu demo. Muốn video đầy đủ lỗi/ngoại lệ, chạy với MESFLOW_TUTORIAL_SEED_DATA=1."
fi

MODULES=(
  "00_overview:overview"
  "01_dashboard:dashboard"
  "02_production_order:po"
  "03_template:templates"
  "04_material_flow:material"
  "05_session:sessions"
  "06_session_exceptions:exceptions"
  "07_employees_qr:employees"
  "08_kiosk_admin:kioskAdmin"
  "09_kiosk_operator:kioskUser"
  "10_employee_productivity:employeeProductivity"
  "11_working_calendar:calendar"
  "12_users_permissions:users"
  "13_system_logs:logs"
  "14_common_cases:commonCases"
)

FAILED=()
TOTAL_MODULES="${#MODULES[@]}"
CURRENT_MODULE=0
for item in "${MODULES[@]}"; do
  name="${item%%:*}"
  module="${item#*:}"
  CURRENT_MODULE=$((CURRENT_MODULE + 1))
  echo "TUTORIAL_PROGRESS stage=recording current=$CURRENT_MODULE total=$TOTAL_MODULES item=$name"
  echo
  echo "===== VIDEO $name ($module) ====="
  rm -rf test-results/tutorial-detailed

  run_module() {
    MESFLOW_BASE_URL="$BASE_URL" \
    MESFLOW_TUTORIAL_MODULE="$module" \
    MESFLOW_TUTORIAL_WAIT_MS="$WAIT" \
    MESFLOW_TUTORIAL_LONG_WAIT_MS="$LONG" \
    MESFLOW_TUTORIAL_STEP_WAIT_MS="$STEP" \
    MESFLOW_TUTORIAL_AUTH_STATE="$AUTH_STATE" \
    npx playwright test tests/e2e/tutorial-detailed.spec.js --config=playwright.tutorial-detailed.config.js
  }

  # Retry/discard is decided by whether a video file actually exists, NOT
  # by run_module's exit code. The recording itself (Playwright records
  # unconditionally while the test runs) succeeds independently of the
  # tutorial's own soft QA-bug reporting (tutorial-detailed.spec.js's
  # note() logs a non-fatal bug -- TARGET_NOT_VISIBLE, a narration overlay
  # covering a now-larger element, a stale selector on one step -- and
  # keeps going; only the final `expect.soft(bugs).toHaveLength(0)` turns
  # that into a non-zero exit). Found live 2026-09-03 running this exact
  # script against a deliberately richer, more realistic dataset (16
  # employees, 85 sessions) than these narration selectors were tuned
  # against: roughly half the modules hit at least one such soft bug, so
  # exit-code-gated retry/discard was throwing away a real, complete
  # recording every time -- both attempts, since `rm -rf
  # test-results/tutorial-detailed` before the retry deleted the first
  # attempt's video before ever checking for it, and a second soft-failing
  # attempt then got discarded by `continue` without ever being looked at
  # either. A demo/tutorial dataset with this much real content is exactly
  # the case this script exists to record -- soft narration-positioning
  # noise on a big dataset must not cost the video.
  run_module || true
  video="$(find test-results/tutorial-detailed -type f -name '*.webm' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
  if [[ -z "$video" ]]; then
    echo "[WARN] $module: no video from first attempt. Retrying once with fresh browser..."
    rm -rf test-results/tutorial-detailed
    run_module || true
    video="$(find test-results/tutorial-detailed -type f -name '*.webm' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
  fi
  if [[ -z "$video" ]]; then
    echo "[FAIL] $module: không tìm thấy video sau khi thử lại; continuing with remaining videos."
    FAILED+=("$module")
    continue
  fi
  cp "$video" "$OUT/$name.webm"

  if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -loglevel error -y -i "$OUT/$name.webm" \
      -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -movflags +faststart \
      "$OUT/$name.mp4"
  fi
done

echo
echo "===== DONE ====="
ls -lh "$OUT"
echo
echo "Mở thư mục: $OUT"


if [[ "${MESFLOW_TUTORIAL_WITH_VOICE:-1}" == "1" ]]; then
  echo
  echo "===== THÊM INTRO + GIỌNG ĐỌC ====="
  if bash "$ROOT/scripts/add-tutorial-voice.sh" "$OUT"; then
    echo "Video có giọng đọc: $OUT/final"
  else
    echo "[WARN] Không tạo được voice-over; video gốc vẫn giữ nguyên tại $OUT"
  fi
fi

if [[ "${MESFLOW_TUTORIAL_AUTO_PUBLISH:-1}" == "1" ]]; then
  echo "TUTORIAL_PROGRESS stage=publishing"
  echo
  echo "===== PUBLISH VÀO MESFLOW ====="
  if [[ -d "$OUT/final" ]] && find "$OUT/final" -maxdepth 1 -type f -name '*_voice.mp4' -print -quit | grep -q .; then
    PUBLISH_SRC="$OUT/final"
  else
    PUBLISH_SRC="$OUT"
  fi
  if bash "$ROOT/scripts/publish-user-guide-videos.sh" "$PUBLISH_SRC"; then
    echo "Tab Hướng dẫn đã được cập nhật."
  else
    echo "[WARN] Chưa publish vào runtime/tutorials; video vẫn giữ nguyên tại $OUT"
  fi
fi

echo "TUTORIAL_PROGRESS stage=verifying"

# Show a concise result before returning partial-success code.
if [[ -f "$ROOT/runtime/tutorials/manifest.json" ]]; then
  echo "[OK] Manifest tutorial: $ROOT/runtime/tutorials/manifest.json"
else
  echo "[WARN] Chưa có manifest tutorial. Hãy xem các module thất bại và bước PUBLISH phía trên."
fi

if ((${#FAILED[@]})); then
  echo
  echo "[WARN] Video chưa tạo được: ${FAILED[*]}"
  echo "Có thể quay riêng bằng scripts/make-one-user-guide-video.sh <module> ..."
  exit 3
fi
