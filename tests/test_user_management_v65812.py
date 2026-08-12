from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_user_management_sources():
    s=(ROOT/'app/mesflow/web/users.py').read_text()
    js=(ROOT/'app/mesflow/web/static/app.js').read_text()
    assert "@bp.get('/users')" in s
    assert 'reset-password' in s
    assert 'change-password' in s
    assert 'renderUsers' in js
    assert 'Người dùng' in js
