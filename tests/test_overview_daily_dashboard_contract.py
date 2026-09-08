from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_overview_page_and_api_are_wired():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    page=(ROOT/'app/mesflow/web/static/pages/overview.js').read_text()
    routes=(ROOT/'app/mesflow/web/analytics.py').read_text()
    repo=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text()
    html=(ROOT/'app/mesflow/web/templates/app.html').read_text()
    assert "page:'overview'" in app
    assert "renderOverview()" in app
    assert "/api/dashboard/overview" in page
    assert "@bp.get('/dashboard/overview')" in routes
    assert "def operation_overview" in repo
    assert "/static/pages/overview.js" in html

def test_daily_dashboard_uses_one_date_filter_and_full_day_endpoint():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    repo=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text()
    assert "id=\"dailyDate\"" in app
    routes=(ROOT/'app/mesflow/web/analytics.py').read_text()
    assert "id=\"dailyShift\"" not in app
    assert 'data-dashboard-tab="overview">A · Tổng quan Operation</button>' in app
    # The overview pane's active/hidden state is data-driven (tab= URL
    # state, see test_daily_dashboard_tab_and_date_reflect_in_url below), not
    # a fixed literal -- assert the pane exists with the right role, not the
    # exact attribute string that used to be hard-coded.
    assert 'data-dashboard-pane="overview" role="tabpanel"' in app
    assert "/api/dashboard/day?date=${encodeURIComponent(date)}" in app
    assert "@bp.get('/dashboard/day')" in routes
    assert "calendar_day:bool=False" in repo
    assert "self._calendar_day_context(shift_date) if calendar_day" in repo
    assert "ws.started_at < %s AND COALESCE(ws.ended_at,CURRENT_TIMESTAMP) >= %s" in repo

def test_daily_dashboard_tab_and_date_reflect_in_url():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    # Dashboard theo ngày's 3 tabs (overview/people/output) + date filter
    # round-trip through the URL (query params, replaceState) so refresh,
    # deep-link and browser Back/Forward restore the exact same tab + date --
    # the same replace-by-default convention Session Management's
    # syncSessionUrl() already uses for its own filters. No shift/ca param:
    # this dashboard only ever filters by date.
    assert "dashboardTabIds=['overview','people','output']" in app
    assert "dashQuery.get('tab')" in app
    assert "dashQuery.get('date')" in app
    assert "AppNav.setQuery({tab:" in app
