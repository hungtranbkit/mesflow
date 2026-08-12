from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E="65.8.44.45"

def test_version():
 assert (R/"VERSION.txt").read_text().strip()==E
 assert E in (R/"app/mesflow/__init__.py").read_text()
 assert json.loads((R/"release.json").read_text())["version"]==E

def test_shared_auth_state_created_once():
 s=(R/"scripts/make-user-guide-video.sh").read_text()
 assert "ĐĂNG NHẬP MỘT LẦN CHO TOÀN BỘ VIDEO" in s
 assert "tutorial-auth-state.js" in s
 assert 'MESFLOW_TUTORIAL_AUTH_STATE="$AUTH_STATE"' in s

def test_playwright_loads_storage_state():
 s=(R/"playwright.tutorial-detailed.config.js").read_text()
 assert "storageState:" in s and "fs.existsSync(authState)" in s

def test_tour_reuses_existing_session():
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 block=s[s.index("async function login(page)"):s.index("async function open(page")]
 assert "/api/auth/me" in block
 assert "rate limiter" in block

def test_auth_helper_retries_429():
 s=(R/"tests/e2e/tutorial-auth-state.js").read_text()
 assert "r.status()===429" in s
 assert "attempt<=8" in s
 assert "storageState" in s

def test_publish_metadata_is_user_friendly():
 s=(R/"scripts/publish-user-guide-videos.sh").read_text()
 for x in ["Lệnh sản xuất","Mẫu quy trình","Dòng vật tư","Phiên làm việc bất thường","Trạm thao tác cho công nhân"]:
  assert x in s
