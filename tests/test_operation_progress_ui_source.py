from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def _js():
    return (ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')

def _daily_progress_fn():
    """Isolate DashboardRepository.daily_progress() -- the query backing
    both /api/dashboard/shift and /api/dashboard/daily-progress -- by its
    start/end markers, the same way the source is organized (one method per
    def)."""
    source=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
    start='def daily_progress(self,'
    end='\n    def daily_sessions(self,'
    assert start in source and end in source
    return source.split(start,1)[1].split(end,1)[0]

def test_backend_active_workers_is_filtered_by_open_status():
    """Regression guard for the root cause: the old workers aggregate in
    daily_progress() had no FILTER at all, so it collected every employee
    who ever touched the Operation in the window, ended sessions included."""
    fn=_daily_progress_fn()
    assert "FILTER (WHERE ds.status='OPEN') active_workers" in fn
    # DISTINCT is on the whole (employee_id,name) object -- see
    # uq_open_session_per_employee, an employee can hold at most one OPEN
    # session at all, so this is already DISTINCT by employee_id.
    assert "jsonb_agg(DISTINCT jsonb_build_object('employee_id',ds.employee_id,'name',e.name))" in fn
    assert "all_participants" in fn
    # The old unfiltered aggregate must be gone from this query, not just shadowed.
    assert "STRING_AGG(DISTINCT e.name,', ' ORDER BY e.name) workers" not in fn
    # total_sessions / running_sessions stay exactly as before (unchanged predicate).
    assert "COUNT(ds.id) session_count" in fn
    assert "COUNT(ds.id) FILTER (WHERE ds.status='OPEN') open_session_count" in fn

def test_active_workers_ui_helpers_defined():
    js=_js()
    assert 'function activeWorkersLabel(x)' in js
    assert 'function activeWorkersTitle(x)' in js
    # running_sessions=0 -> explicit copy, never a silently blank '—' that
    # could be confused with "chưa tải xong", and never a historical name.
    assert "'Không có người đang làm'" in js
    assert 'Đã tham gia trước đó' in js  # optional history stays in a tooltip only

def test_workers_column_render_sites_use_active_workers_only():
    js=_js()
    # 1 definition + the 3 render sites ("Tiến độ theo Operation", "OP phát
    # sinh" daily attention panel, "Danh sách OP phát sinh" full list page).
    assert js.count('activeWorkersLabel(x)') == 4
    # The raw historical field must not be read anywhere any more.
    assert 'x.workers' not in js
