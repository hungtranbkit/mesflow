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


def test_thresholds_are_one_constant_not_scattered_magic_numbers():
    js = _js()
    assert 'const EMPLOYEE_PRODUCTIVITY_THRESHOLDS' in js
    # The exact bands from the task spec.
    for min_value in ('{ min: 100,', '{ min: 80,', '{ min: 60,', '{ min: -Infinity,'):
        assert min_value in js
    # Every render site reads through the one function, not inline comparisons.
    assert js.count('productivityBand(') >= 2


def test_average_definition_matches_spec_default_sort_and_no_clamp():
    js = _js()
    # Default sort: productivity descending.
    assert "sortDir = -1" in js
    # Section 5: the displayed percent text must never be clamped at 100%.
    assert 'function productivityText' in js
    fn_body = js.split('function productivityText', 1)[1].split('\nfunction ', 1)[0]
    assert 'Math.min(' not in fn_body
    assert 'Math.max(' not in fn_body


def test_detail_view_shows_running_and_insufficient_data_distinctly():
    js = _js()
    assert 'Đang chạy' in js
    assert 'Không đủ dữ liệu' in js
