#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${MESFLOW_TUTORIAL_PUBLISH_DIR:-$ROOT/runtime/tutorials}"
GROUP="${MESFLOW_TUTORIAL_GROUP:-$(id -gn)}"
echo "Chuẩn bị quyền thư viện video: $DEST"
sudo install -d -o "$USER" -g "$GROUP" -m 2775 "$DEST"
sudo chown -R "$USER:$GROUP" "$DEST"
sudo find "$DEST" -type d -exec chmod 2775 {} +
sudo find "$DEST" -type f -exec chmod 664 {} +
echo "OK: $USER có thể publish video vào $DEST"
