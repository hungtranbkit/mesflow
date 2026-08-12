#!/usr/bin/env bash
set -Eeuo pipefail
VIDEO_DIR="${1:-$HOME/mesflow-user-guide}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NARR="$ROOT/tutorial/narration"
VOICE="${MESFLOW_TTS_VOICE:-vi-VN-HoaiMyNeural}"
RATE="${MESFLOW_TTS_RATE:--8%}"
INTRO_SEC="${MESFLOW_TUTORIAL_INTRO_SECONDS:-4}"

command -v ffmpeg >/dev/null || { echo "[ERROR] Cần ffmpeg: sudo apt install -y ffmpeg"; exit 2; }

if command -v edge-tts >/dev/null 2>&1; then
  TTS=edge
elif command -v espeak-ng >/dev/null 2>&1; then
  TTS=espeak
else
  echo "[ERROR] Chưa có TTS. Khuyên dùng: python3 -m pip install --user edge-tts"
  echo "Fallback offline: sudo apt install -y espeak-ng"
  exit 2
fi

mkdir -p "$VIDEO_DIR/voice" "$VIDEO_DIR/final"
shopt -s nullglob
for txt in "$NARR"/*.txt; do
  name="$(basename "$txt" .txt)"
  src="$VIDEO_DIR/$name.mp4"
  [[ -f "$src" ]] || src="$VIDEO_DIR/$name.webm"
  [[ -f "$src" ]] || { echo "[SKIP] $name: chưa có video"; continue; }

  wav="$VIDEO_DIR/voice/$name.wav"
  audio="$VIDEO_DIR/voice/$name.mp3"
  title="${name#*_}"; title="${title//_/ }"

  echo "===== VOICE $name ====="
  if [[ "$TTS" == edge ]]; then
    edge-tts --voice "$VOICE" --rate="$RATE" --file "$txt" --write-media "$audio"
  else
    espeak-ng -v vi -s 135 -f "$txt" -w "$wav"
    ffmpeg -loglevel error -y -i "$wav" -codec:a libmp3lame -q:a 3 "$audio"
  fi

  # Intro: dark clean title card + short soft tone. No external assets required.
  intro="$VIDEO_DIR/voice/${name}_intro.mp4"
  ffmpeg -loglevel error -y \
    -f lavfi -i "color=c=0x0d2035:s=1920x1080:d=$INTRO_SEC:r=30" \
    -f lavfi -i "sine=frequency=523:duration=0.22:sample_rate=48000" \
    -filter_complex "[0:v]drawtext=text='MESFlow':fontcolor=white:fontsize=92:x=(w-text_w)/2:y=(h-text_h)/2-70,drawtext=text='${title}':fontcolor=white:fontsize=44:x=(w-text_w)/2:y=(h-text_h)/2+65[v];[1:a]volume=0.10,apad=whole_dur=${INTRO_SEC}[a]" \
    -map "[v]" -map "[a]" -t "$INTRO_SEC" -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 "$intro"

  # Intro is concatenated later, so narration starts immediately with the body.
  # Body duration is max(video,narration): hold last frame or pad audio as needed.
  vdur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src" | head -1)"
  adur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$audio" | head -1)"
  body_dur="$(python3 - "$vdur" "$adur" <<'PY'
import sys
print(f"{max(float(sys.argv[1] or 0),float(sys.argv[2] or 0))+0.15:.3f}")
PY
)"
  voiced="$VIDEO_DIR/voice/${name}_voiced.mp4"
  ffmpeg -loglevel error -y -i "$src" -i "$audio" \
    -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,tpad=stop_mode=clone:stop_duration=${body_dur},format=yuv420p[v];[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur=${body_dur}[a]" \
    -map "[v]" -map "[a]" -t "$body_dur" -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p \
    -c:a aac -b:a 160k -ar 48000 -ac 2 "$voiced"

  # Normalize intro and body then concatenate.
  list="$VIDEO_DIR/voice/${name}_concat.txt"
  printf "file '%s'\nfile '%s'\n" "$intro" "$voiced" > "$list"
  ffmpeg -loglevel error -y -f concat -safe 0 -i "$list" -c copy "$VIDEO_DIR/final/${name}_voice.mp4" || \
    ffmpeg -loglevel error -y -i "$intro" -i "$voiced" \
      -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" \
      -map "[v]" -map "[a]" -c:v libx264 -c:a aac "$VIDEO_DIR/final/${name}_voice.mp4"
done

echo
echo "===== VOICE TUTORIAL DONE ====="
ls -lh "$VIDEO_DIR/final"
