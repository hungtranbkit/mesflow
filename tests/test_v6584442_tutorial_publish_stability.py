from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]; EXPECTED=(R/"VERSION.txt").read_text().strip()
def test_release_sync():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 assert f"mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()
def test_publish_after_voice():
 s=(R/"scripts/make-user-guide-video.sh").read_text(); assert s.index("THÊM INTRO + GIỌNG ĐỌC") < s.index("PUBLISH VÀO MESFLOW"); assert "*_voice.mp4" in s
def test_publisher_order():
 s=(R/"scripts/publish-user-guide-videos.sh").read_text(); line=[x for x in s.splitlines() if "for candidate in" in x][0]; assert line.index("${key}_voice.mp4") < line.index("${key}.mp4") < line.index("${key}.webm")
def test_atomic_manifest():
 s=(R/"scripts/publish-user-guide-videos.sh").read_text(); assert ".manifest.json.tmp.$$" in s and "giữ manifest cũ" in s and 'mv -f "$tmp_manifest" "$DEST/manifest.json"' in s
def test_repair_script():
 s=(R/"scripts/repair-tutorial-publish-permissions.sh").read_text(); assert "chmod 2775" in s and "chown -R" in s
def test_setup_2775():
 assert "-m 2775 /opt/mesflow/runtime/tutorials" in (R/"scripts/setup-tutorial-audio-ubuntu.sh").read_text()
