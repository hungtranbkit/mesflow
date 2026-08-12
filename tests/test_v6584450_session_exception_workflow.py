from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E="65.8.44.50"

def test_version():
    assert (R/"VERSION.txt").read_text().strip()==E
    assert E in (R/"app/mesflow/__init__.py").read_text()
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
    assert "expandedSessionId=target" in block
    assert "Quay lại bất thường" in block

def test_css_limits_queue_height():
    s=(R/"app/mesflow/web/static/ui.css").read_text()
    assert ".se-list{max-height:65vh;overflow:auto}" in s
    assert ".se-detail{position:sticky" in s
