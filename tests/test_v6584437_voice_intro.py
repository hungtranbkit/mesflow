from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
def test_release():
 version=(R/"VERSION.txt").read_text().strip()
 assert json.loads((R/"release.json").read_text())["version"]==version
 assert f"mesflow-app:{version}" in (R/"compose.yml").read_text()
def test_narration_all_modules():
 p=R/"tutorial/narration"
 # A 14th module (13_common_cases.txt) was added after this test was
 # written -- a real, deliberate content expansion, not drift to paper
 # over. The real invariant this test cares about (every module has
 # substantial narration text) still holds for all of them.
 assert len(list(p.glob("*.txt")))==14
 for f in p.glob("*.txt"): assert len(f.read_text().strip())>80
def test_audio_pipeline():
 s=(R/"scripts/add-tutorial-voice.sh").read_text()
 assert "edge-tts" in s and "espeak-ng" in s and "ffmpeg" in s
 assert "INTRO_SEC" in s and "/final/" in s
def test_batch_auto_voice():
 s=(R/"scripts/make-user-guide-video.sh").read_text()
 assert "MESFLOW_TUTORIAL_WITH_VOICE:-1" in s
 assert "add-tutorial-voice.sh" in s
