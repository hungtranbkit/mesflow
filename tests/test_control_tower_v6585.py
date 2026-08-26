from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_current_dashboard_frontend_sections():
    js=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    for marker in ('/api/dashboard/shift','shift_date','shift_id','employee-day-row','session-management'):
        assert marker in js

def test_shift_dashboard_backend_contract():
    analytics=(ROOT/'app/mesflow/web/analytics.py').read_text(encoding='utf-8')
    shifts=(ROOT/'app/mesflow/core/working_calendar.py').read_text(encoding='utf-8')
    assert "url_prefix='/api'" in analytics or 'url_prefix="/api"' in analytics
    assert "@bp.get('/dashboard/shift')" in analytics or '@bp.get("/dashboard/shift")' in analytics
    assert 'shift_date' in analytics and 'shift_id' in analytics
    assert 'cross_midnight' in shifts

def test_release_version_6585():
    version=(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (65,8,33)
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==version
