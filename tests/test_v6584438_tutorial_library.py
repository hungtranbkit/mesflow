from pathlib import Path
import json, ast
R=Path(__file__).resolve().parents[1]
EXPECTED=(R/"VERSION.txt").read_text().strip()

def test_release_sync():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 assert f"mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()

def test_persistent_mount():
 c=(R/"compose.yml").read_text()
 assert "./runtime/tutorials:/data/tutorials:ro" in c
 assert "MESFLOW_TUTORIAL_DIR: /data/tutorials" in c

def test_backend_manifest_and_video_are_authenticated():
 a=(R/"app/mesflow/web/app.py").read_text()
 ast.parse(a)
 assert "@app.get('/api/tutorials')" in a
 assert "@app.get('/tutorials/<path:filename>')" in a
 assert "AUTH_REQUIRED" in a
 assert "target.relative_to(tutorial_root)" in a or "candidate.relative_to(tutorial_root)" in a

def test_frontend_tutorial_tab():
 s=(R/"app/mesflow/web/static/app.js").read_text()
 # Menu/page-title label was later shortened site-wide from "Hướng dẫn sử
 # dụng" to "Hướng dẫn" (see the menu array and renderTutorials()'s own
 # title.textContent) -- the feature itself is unchanged.
 assert "Hướng dẫn" in s
 assert "renderTutorials()" in s
 # renderTutorials() later switched from an /api/tutorials JSON call to
 # fetching the static manifest directly (still same-origin authenticated
 # via the session cookie) -- the backend route itself is unchanged (see
 # test_backend_manifest_and_video_are_authenticated above).
 assert "/tutorials/manifest.json" in s
 assert "tutorialVideo" in s

def test_publish_contract():
 s=(R/"scripts/publish-user-guide-videos.sh").read_text()
 assert "runtime/tutorials" in s
 assert "manifest.json" in s
 assert "09_kiosk_operator" in s
 assert "11_users_permissions" in s

def test_setup_uses_pipx_not_break_system_python():
 s=(R/"scripts/setup-tutorial-audio-ubuntu.sh").read_text()
 assert "pipx install edge-tts" in s
 assert "pip install --user" not in s
 assert "--break-system-packages" not in s
