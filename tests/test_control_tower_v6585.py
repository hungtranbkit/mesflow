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
    assert tuple(map(int,(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip().split('.'))) >= (65,8,33)
    version=(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip()
    assert f"__version__='{version}'" in (ROOT/'app/mesflow/__init__.py').read_text(encoding='utf-8').replace(' ', '')
