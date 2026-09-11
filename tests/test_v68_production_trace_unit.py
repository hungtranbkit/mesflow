from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from mesflow.services.production_trace_service import TraceEvent
ROOT=Path(__file__).parents[1]
def test_trace_event_normalized_contract():
    e=TraceEvent('1','SESSION_STARTED','SESSION',datetime.now(timezone.utc),1,'admin',2,3,4,5,'Bắt đầu','',None,{},'corr','session-trace','NATIVE')
    assert set(asdict(e))=={'id','event_type','category','occurred_at','actor_id','actor_name','po_id','part_id','operation_id','session_id','title','description','quantity_delta','metadata','correlation_id','session_trace_id','source'}
def test_v68_schema_is_append_only_and_indexed():
    s=(ROOT/'app/migrations/versions/0032_v68_production_trace.py').read_text()
    assert "down_revision='0031_v67_exception_center'" in s
    assert 'CREATE TABLE production_trace_events' in s and 'CREATE TABLE quantity_movements' in s
    for key in ('idx_trace_po_time','idx_trace_operation_time','idx_trace_session_time','idx_trace_correlation','idx_trace_session_trace','idx_quantity_session_time'):assert key in s
    assert 'UPDATE quantity_movements' not in s and 'UPDATE production_trace_events' not in s
def test_read_model_marks_legacy_inference_and_keeps_sources_distinct():
    s=(ROOT/'app/mesflow/services/production_trace_service.py').read_text()
    for source in ('LEGACY_DERIVED','V67_EXCEPTION','KIOSK','AUDIT','NATIVE'):assert source in s
    assert 'Input Consumption' not in s


# --- REQ-TRACE-001: màn hình luôn mở sẵn một PO ----------------------------
#
# Kiểm NGUỒN chứ không kiểm hành vi ở đây là cố ý: hành vi đúng đã có bài e2e
# (tests/e2e/production-trace-v68.spec.js). Thứ bài dưới đây giữ là các QUYẾT
# ĐỊNH dễ bị một lần sửa vô tình xoá đi mà màn hình vẫn "chạy được": option
# rỗng quay lại, PO chọn giúp không vào URL, hoặc màn này tự viết lại thứ hạng
# PO thay vì dùng chung với Kiosk/Dashboard.
def _code_only(source: str) -> str:
    """Bỏ dòng chú thích trước khi quét.

    Chú thích nhắc lại chuỗi cũ để GIẢI THÍCH vì sao nó sai không phải là một
    lần tái phạm. Quét cả chú thích thì bài test tự cấm việc ghi lại bài học --
    đúng thứ ta muốn giữ (cùng lý do với test_po_status_policy_is_single_sourced).
    """
    return '\n'.join(line for line in source.split('\n')
                     if not line.lstrip().startswith(('//', '*', '/*')))


TRACE_PAGE = _code_only(
    (ROOT / 'app/mesflow/web/static/pages/production-trace.js').read_text(encoding='utf-8'))


def test_the_po_selector_has_no_empty_placeholder_option():
    assert 'Chọn PO cần truy vết' not in TRACE_PAGE, (
        'option rỗng nghĩa là màn hình mở ra không xem PO nào — REQ-TRACE-001')
    assert '<option value="">' not in TRACE_PAGE


def test_the_default_po_comes_from_the_shared_ranking_not_a_local_copy():
    assert '/api/kiosk-board/po-options' in TRACE_PAGE, (
        'thứ hạng "PO nào đang chạy" phải dùng chung với Kiosk/Dashboard '
        '(REQ-DASH-006 §4), không được chép lại ở trình duyệt')
    assert 'include_id=' in TRACE_PAGE, 'PO đang xem phải được ghim vào bộ chọn'


def test_the_viewed_po_is_written_to_the_url():
    assert 'AppNav.setQuery({po_id' in TRACE_PAGE, (
        'po_id phải nằm trong URL, nếu không refresh/Back-Forward mất context')
    assert "URLSearchParams(location.search).get('po_id')" in TRACE_PAGE


def test_an_unknown_po_is_never_silently_replaced():
    assert 'Không mở được Production Order' in TRACE_PAGE, (
        'đổi PO sau lưng người dùng phải được NÓI RA, không im lặng')


def test_the_empty_state_is_about_data_not_about_a_missing_click():
    assert 'Chưa có Production Order nào' in TRACE_PAGE
    assert 'Chưa chọn Production Order' not in TRACE_PAGE
