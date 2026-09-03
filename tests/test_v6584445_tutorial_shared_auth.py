from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()

def test_version():
 assert (R/"VERSION.txt").read_text().strip()==E
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==E  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
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
 # 2026-09-03: rewritten to log in via a real page instead of the lighter
 # context.request client (that client doesn't get the Secure-cookie
 # trustworthy-origin treatment a real browser network call does, so the
 # /api/auth/me verification silently failed every time against a plain
 # http:// target -- found live running this exact script). The login
 # response variable is now named `response` (from page.waitForResponse),
 # not `r`; same retry/backoff/storageState contract otherwise.
 assert "response.status()===429" in s
 assert "attempt<=8" in s
 assert "storageState" in s

def test_publish_metadata_is_user_friendly():
 s=(R/"scripts/publish-user-guide-videos.sh").read_text()
 for x in ["Lệnh sản xuất","Mẫu quy trình","Dòng vật tư","Phiên làm việc bất thường","Trạm thao tác cho công nhân"]:
  assert x in s
