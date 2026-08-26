from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]; EXPECTED=(R/"VERSION.txt").read_text().strip()
def test_version():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
 assert f"mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()
def test_no_illegal_filter_mix():
 s=(R/"scripts/add-tutorial-voice.sh").read_text()
 assert '-c:a aac -b:a 160k -af apad' not in s
 assert 'apad=whole_dur=${body_dur}' in s
def test_no_double_delay():
 assert "adelay=" not in (R/"scripts/add-tutorial-voice.sh").read_text()
def test_duration_extension():
 s=(R/"scripts/add-tutorial-voice.sh").read_text()
 assert "ffprobe" in s and "tpad=stop_mode=clone" in s and 'body_dur=' in s
