# Codex audit E2E finding (Blocker 9/10): pages/session-exceptions.js,
# which every test below reads, was found to be DEAD CODE during a live
# Playwright run -- app.html loads pages/exception-center.js right after
# it, and exception-center.js unconditionally does
# `renderSessionExceptions=ExceptionCenter.render`, permanently overwriting
# the same global. The Exception Center screen a real browser renders is
# exception-center.js's 5-tab UI (calling /api/exceptions), never
# session-exceptions.js's 3-tab/workflow-status UI (calling
# /api/session-exceptions) that these tests describe. The dead <script>
# tag has been removed from app.html (see its own comment there).
#
# The assertions below are still an ACCURATE description of
# pages/session-exceptions.js's own source text -- left as-is rather than
# rewritten, since deciding whether that richer implementation should
# actually REPLACE exception-center.js (and verifying /api/session-exceptions
# has equivalent reconciliation guarantees to /api/exceptions first) is a
# real product decision, not something to resolve inside a test fix.
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()

def test_version():
 assert (R/"VERSION.txt").read_text().strip()==E
 assert json.loads((R/"release.json").read_text())["version"]==E

def test_receive_modal_is_action_focused():
 s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
 assert "Nhận và mở Session" in s
 assert "Chỉ nhận xử lý" in s
 assert "Tôi xử lý" in s
 assert "Bước tiếp theo" in s

def test_receive_defaults_to_current_user():
 s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
 assert "window.MESFLOW_USER?.username" in s
 assert "current.assigned_to||currentUser" in s

def test_claim_and_open_deeplinks_session():
 s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
 assert "openSessionAfter" in s
 assert "MESFLOW_SESSION_EXCEPTION_CONTEXT" in s
 # Toast wording was later split into one short message per target status
 # ('Đã nhận xử lý' for IN_PROGRESS) instead of one combined sentence --
 # the claim-then-open behavior itself (openSessionAfter&&targetStatus===
 # 'IN_PROGRESS') is unchanged, see the assertion above.
 assert "Đã nhận xử lý" in s

def test_backend_falls_back_assignee_to_actor():
 s=(R/"app/mesflow/web/analytics.py").read_text()
 assert "target_status=='IN_PROGRESS' and not assigned_to" in s
 assert "assigned_to=current_actor" in s

def test_receive_does_not_require_resolution():
 s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
 assert "seResolutionWrap').hidden=!isFinish" in s
 assert "targetStatus==='RESOLVED'&&!el('seResolution').value" in s
