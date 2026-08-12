from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E="65.8.44.51"

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
 assert "Đã nhận xử lý. Đang mở Session cần kiểm tra" in s

def test_backend_falls_back_assignee_to_actor():
 s=(R/"app/mesflow/web/analytics.py").read_text()
 assert "target_status=='IN_PROGRESS' and not assigned_to" in s
 assert "assigned_to=current_actor" in s

def test_receive_does_not_require_resolution():
 s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
 assert "seResolutionWrap').hidden=!isFinish" in s
 assert "targetStatus==='RESOLVED'&&!el('seResolution').value" in s
