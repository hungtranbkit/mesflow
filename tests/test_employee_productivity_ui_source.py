"""Báo cáo năng suất nhân viên -- UI wiring + threshold-constant contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return (ROOT / 'app/mesflow/web/static/pages/employee-productivity.js').read_text(encoding='utf-8')


def _app_js():
    return (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')


def test_menu_entry_not_inside_employee_crud_screen():
    js = _app_js()
    assert "{page:'employee-productivity',label:'Báo cáo năng suất nhân viên'" in js
    # Must live in the "Điều hành" group, not bolted onto the Employees CRUD resource.
    executive_block = js[js.index("{label:'Điều hành'"):js.index("{label:'Danh mục'")]
    assert 'employee-productivity' in executive_block
    assert "'employee-productivity':'session.view'" in js  # PAGE_PERMISSION entry, consistent with sibling reports


def test_page_module_registered_after_app_js():
    html = (ROOT / 'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    app_pos = html.index('src="/static/app.js')
    page_pos = html.index('src="/static/pages/employee-productivity.js')
    assert page_pos > app_pos


def test_openpage_routing_is_additive_not_editing_app_js():
    js = _js()
    assert 'const openPageWithoutProductivity = openPage;' in js
    assert "id === 'employee-productivity'" in js
    assert 'return openPageWithoutProductivity(id, btn);' in js


def test_average_definition_matches_spec_default_sort_and_no_clamp():
    js = _js()
    # Default sort: productivity descending.
    assert "sortDir = -1" in js
    # Section 5: the displayed percent text must never be clamped at 100%.
    assert 'function productivityText' in js
    fn_body = js.split('function productivityText', 1)[1].split('\nfunction ', 1)[0]
    assert 'Math.min(' not in fn_body
    assert 'Math.max(' not in fn_body


def test_detail_view_shows_insufficient_data_not_running_state():
    """2026-08-22 revision: this report is completed-session-only -- the
    detail view must never render a running/live session state at all
    (there is nothing left in the API response to render it from), while
    still distinguishing "closed but missing a standard rate" sessions."""
    js = _js()
    assert 'Không đủ dữ liệu' in js
    assert 'Đang chạy' not in js
    assert "status === 'OPEN'" not in js


def test_report_never_renders_realtime_worker_state():
    """Section 3/4/7: no running_sessions/active worker/current-Operation
    field or label anywhere in this page's source -- the whole screen is
    completed-session-only."""
    js = _js()
    for forbidden in ('running_sessions', 'active_employee_count', 'Đang làm việc', 'top_employee'):
        assert forbidden not in js, f'{forbidden!r} must not appear -- this report is completed-session-only'


def test_kpis_match_the_four_required_completed_session_cards():
    js = _js()
    for label in ('Nhân viên có dữ liệu', 'Tổng Session đã kết thúc', 'Năng suất trung bình', 'Tổng sản lượng đạt'):
        assert label in js


def test_main_table_uses_completed_sessions_field():
    js = _js()
    assert 'x.completed_sessions' in js
    assert 'x.running_sessions' not in js
