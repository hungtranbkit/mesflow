from pathlib import Path
import json, ast
R=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.38"

def test_release_sync():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 assert EXPECTED in (R/"app/mesflow/__init__.py").read_text()
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 assert f"image: mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()

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
 assert "Hướng dẫn sử dụng" in s
 assert "renderTutorials()" in s
 assert "/api/tutorials" in s
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
