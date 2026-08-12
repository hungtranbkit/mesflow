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

def test_daily_dashboard_keeps_explicit_date_and_shift():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    repo=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text()
    assert "id=\"dailyDate\"" in app
    assert "id=\"dailyShift\"" in app
    assert "shift_date=${encodeURIComponent(date)}" in app
    assert "resolve_shift_context(shift_date,shift_id)" in repo
    assert "ws.started_at < %s AND COALESCE(ws.ended_at,CURRENT_TIMESTAMP) >= %s" in repo
