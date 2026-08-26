# Codex audit E2E finding: window.MESFLOW_SESSION_EXCEPTION_CONTEXT (read by
# renderSessionManagement()'s deep-link/back logic below, still live in
# app.js) is only ever SET to a real value inside pages/session-exceptions.js,
# which is confirmed dead code (see test_v6584451_receive_exception_ui.py's
# module docstring) -- its dead <script> tag has been removed from app.html.
# In practice nothing sets this context today, so this receiving code path
# is currently unreachable end-to-end even though it is itself correct and
# still exercised by test_session_management_focus_and_back below.
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()

def test_version():
    assert (R/"VERSION.txt").read_text().strip()==E
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==E  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((R/"release.json").read_text())["version"]==E

def test_exception_history_survives_correction():
    s=(R/"app/mesflow/db/repositories/analytics.py").read_text()
    block=s[s.index("def session_exceptions"):s.index("def update_session_exception_reviews")]
    assert "review_only AS" in block
    assert "false is_active" in block
    assert "Bất thường không còn được phát hiện" in block
    assert "UNION ALL" in block

def test_compact_master_detail_ui():
    s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
    assert 'class="se-split"' in s
    assert 'class="se-queue"' in s
    assert 'class="se-detail"' in s
    assert "Cần xử lý" in s
    assert "Nên làm gì?" in s

def test_real_session_fix_is_part_of_workflow():
    s=(R/"app/mesflow/web/static/pages/session-exceptions.js").read_text()
    assert "Mở Session #" in s
    assert "MESFLOW_SESSION_EXCEPTION_CONTEXT" in s
    assert "openPage('session-management'" in s
    assert "Hoàn tất" in s

def test_session_management_focus_and_back():
    s=(R/"app/mesflow/web/static/app.js").read_text()
    block=s[s.index("async function renderSessionManagement"):s.index("async function renderRolePermissions")]
    assert "MESFLOW_SESSION_EXCEPTION_CONTEXT" in block
    assert "smBackException" in block
    # Deep-link targeting later changed from an `expandedSessionId=target`
    # expand-the-row state to a direct scrollIntoView() on the target
    # session's row -- simpler, same "land on and highlight the session
    # that sent you here" outcome.
    assert 'scrollIntoView({behavior:\'smooth\',block:\'center\'})' in block
    assert "returnContext.sessionId" in block
    assert "Quay lại bất thường" in block

def test_css_limits_queue_height():
    s=(R/"app/mesflow/web/static/ui.css").read_text()
    assert ".se-list{max-height:65vh;overflow:auto}" in s
    assert ".se-detail{position:sticky" in s
