from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "65.8.44.56"


def test_version_declarations_are_synchronized():
    assert (ROOT / "VERSION.txt").read_text().strip() == EXPECTED_VERSION
    assert EXPECTED_VERSION in (ROOT / "app/mesflow/__init__.py").read_text()
    assert json.loads((ROOT / "release.json").read_text())["version"] == EXPECTED_VERSION
    assert f"mesflow-app:{EXPECTED_VERSION}" in (ROOT / "compose.yml").read_text()


def test_repeat_anomaly_uses_a_new_occurrence_without_overwriting_history():
    source = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text()
    block = source[source.index("def session_exceptions"):source.index("def employee_performance")]
    assert "#occurrence:" in block
    assert "completed_review" in block
    assert "active_review" in block
    assert "Không thể mở lại lịch sử" in block


def test_corrected_in_progress_occurrence_remains_visible():
    source = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text()
    block = source[source.index("def session_exceptions"):source.index("def update_session_exception_reviews")]
    assert "review_only AS" in block
    assert "false is_active" in block
    assert "Bất thường không còn được phát hiện" in block


def test_ui_has_three_user_workflow_states_and_history_filters():
    source = (ROOT / "app/mesflow/web/static/pages/session-exceptions.js").read_text()
    assert 'data-se-view="NEW"' in source
    assert 'data-se-view="IN_PROGRESS"' in source
    assert 'data-se-view="HISTORY"' in source
    for field in ("seHistoryFrom", "seHistoryEmployee", "seHistoryPo", "seHistoryType", "seHistoryResult", "seHistoryHandler"):
        assert field in source


def test_ignore_reason_and_exact_session_navigation_remain_required():
    source = (ROOT / "app/mesflow/web/static/pages/session-exceptions.js").read_text()
    repository = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text()
    assert "targetStatus==='IGNORED'" in source
    assert "Phải nhập ghi chú khi kết thúc xử lý" in repository
    assert "Phải nhận xử lý trước khi hoàn tất hoặc bỏ qua" in repository
    assert "MESFLOW_SESSION_EXCEPTION_CONTEXT" in source
    assert "openPage('session-management'" in source
