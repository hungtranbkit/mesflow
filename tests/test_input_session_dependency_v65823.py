from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = (ROOT / 'app/mesflow/db/repositories/execution.py').read_text(encoding='utf-8')
KIOSK = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')


def test_quantity_dependency_checks_source_session_before_start():
    assert "input_flow_enabled" in EXECUTION
    assert "EXISTS(SELECT 1 FROM work_sessions ws WHERE ws.operation_id=o.id) session_started" in EXECUTION
    assert "chưa bắt đầu session" in EXECUTION


def test_same_input_source_does_not_require_source_operation_completed():
    assert "predecessor_id!=input_source_id" in EXECUTION


def test_finish_explains_missing_source_reported_quantity():
    assert "chưa có sản lượng đã báo cáo" in EXECUTION
    assert "kết thúc ít nhất một session OP nguồn" in EXECUTION


def test_kiosk_has_specific_dependency_and_quantity_codes():
    assert "DEP-409" in KIOSK
    assert "QTY-409" in KIOSK
