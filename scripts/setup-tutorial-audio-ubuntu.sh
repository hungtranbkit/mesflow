#!/usr/bin/env bash
set -Eeuo pipefail
echo "Cài ffmpeg + TTS cho MESFlow tutorial..."
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng pipx
pipx ensurepath || true
pipx install edge-tts || pipx upgrade edge-tts || true
sudo install -d -o "$USER" -g "$(id -gn)" -m 2775 /opt/mesflow/runtime/tutorials
echo
echo "Đã cài. edge-tts cho giọng Việt tự nhiên khi có Internet; espeak-ng là fallback offline."
