from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_version():
    assert tuple(map(int,(ROOT/'VERSION.txt').read_text().strip().split('.'))) >= (65,8,33)
def test_test_autologin_server_side():
    app=(ROOT/'app/mesflow/web/app.py').read_text()
    cfg=(ROOT/'app/mesflow/core/config.py').read_text()
    assert '/api/auth/test-auto-login' in app
    assert 'test_auto_login' in cfg
    section=app[app.index("@app.post('/api/auth/test-auto-login')"):app.index("@app.post('/api/auth/login')")]
    assert 'password_hash' not in section
    assert "settings.admin_password" not in section
def test_daily_session_timeline():
    repo=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text()
    web=(ROOT/'app/mesflow/web/analytics.py').read_text()
    js=(ROOT/'app/mesflow/web/static/app.js').read_text()
    assert 'def daily_sessions' in repo
    assert '/dashboard/daily-sessions' in web
    assert 'sessionTimeline' in js and 'employee_name' in js
