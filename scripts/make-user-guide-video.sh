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
cp "$ROOT/tests/e2e/tutorial-auth-state.js" "$WORKSPACE/tests/e2e/"

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
  "10_working_calendar:calendar"
  "11_users_permissions:users"
  "12_system_logs:logs"
  "13_common_cases:commonCases"
)

FAILED=()
for item in "${MODULES[@]}"; do
  name="${item%%:*}"
  module="${item#*:}"
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

  if ! run_module; then
    echo "[WARN] $module failed. Retrying once with fresh browser..."
    rm -rf test-results/tutorial-detailed
    if ! run_module; then
      echo "[FAIL] $module failed twice; continuing with remaining videos."
      FAILED+=("$module")
      continue
    fi
  fi

  video="$(find test-results/tutorial-detailed -type f -name '*.webm' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
  if [[ -z "$video" ]]; then
    echo "[FAIL] Không tìm thấy video cho $module; continuing."
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
