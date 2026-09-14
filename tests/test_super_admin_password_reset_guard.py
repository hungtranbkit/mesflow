"""Một admin thường KHÔNG được đặt lại mật khẩu của tài khoản Super Admin.

Vì sao bài này tồn tại. `super_admin_required()` nói rõ trong docstring của
chính nó: "an ordinary ADMIN session always gets 403, never a silent pass".
create() và update() trong users.py đều đã có chốt "chỉ SUPER_ADMIN mới đụng
được vào SUPER_ADMIN" -- nhưng reset-password thì không, và thiếu đúng một chỗ
đó là đủ để cả hai chốt kia thành vô nghĩa.

Dựng lại được ĐẦU-CUỐI trên 71.0.0.310 (PostgreSQL thật, cùng image đang chạy):

    admin  -> POST /api/users/<id-của-super-admin>/reset-password   -> 200 {"ok":true}
    admin  -> POST /api/auth/login  (username super_admin, mật khẩu vừa đặt) -> 200, role=super_admin
    admin  -> GET  /api/system-health/services                      -> 403
    (sau khi leo quyền) -> GET /api/system-health/services          -> 200

Tức là ranh giới admin/super_admin -- và cả bất biến "không được hạ quyền Super
Admin cuối cùng" -- đều đi vòng được bằng một lần đặt lại mật khẩu.

Bài chạy in-process (create_app + test_client), không cần PostgreSQL: cả hai ca
trả lời TRƯỚC khi chạm cơ sở dữ liệu, nên chúng khoá đúng thứ cần khoá là thứ
tự các chốt, không phải hành vi của kho dữ liệu.
"""
from __future__ import annotations

import pytest

from mesflow.core import session_policy
from mesflow.web import app as app_module
from mesflow.web import users as users_module


@pytest.fixture
def client():
    app = app_module.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _sign_in(client, role):
    with client.session_transaction() as sess:
        sess.update(session_policy.session_fields_for_login(1, f'{role}-user', role))


class _Repo:
    """Kho dữ liệu giả: đủ để trả vai trò tài quản đích và GHI LẠI lần đổi mật khẩu.

    Ghi lại chứ không ném lỗi: trình xử lý lỗi chung của Flask nuốt mọi ngoại lệ
    rồi cố ghi action_log, và lần ghi ĐÓ mới là thứ nổ (không có PostgreSQL) --
    tức là bài kiểm sẽ đỏ vì một lý do chẳng liên quan gì tới chốt quyền.
    """

    calls: list = []

    def __init__(self, role):
        self._role = role

    def get_by_id(self, user_id):
        return {'id': user_id, 'username': 'target', 'role': self._role, 'active': True}

    def set_password(self, user_id, password, must_change):
        _Repo.calls.append((user_id, must_change))


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Chốt quyền là thứ đang kiểm, không phải đường ghi nhật ký."""
    _Repo.calls = []
    monkeypatch.setattr(users_module, '_audit', lambda *a, **k: None)


def test_admin_cannot_reset_a_super_admin_password(client, monkeypatch):
    monkeypatch.setattr(users_module, 'UserRepository', lambda: _Repo('super_admin'))
    _sign_in(client, 'admin')
    response = client.post('/api/users/10/reset-password',
                           json={'password': 'Pwned12345', 'must_change_password': False})
    assert response.status_code == 403, response.get_data(as_text=True)
    assert response.get_json()['error'] == 'FORBIDDEN'


def test_the_blocked_call_never_reaches_the_password_write(client, monkeypatch):
    """Chặn ở HTTP là chưa đủ -- mật khẩu không được đổi trên đường nào cả."""
    monkeypatch.setattr(users_module, 'UserRepository', lambda: _Repo('super_admin'))
    _sign_in(client, 'admin')
    client.post('/api/users/10/reset-password',
                json={'password': 'Pwned12345', 'must_change_password': False})
    assert _Repo.calls == [], 'mật khẩu Super Admin đã bị đổi dù đã trả 403'


def test_a_super_admin_still_can(client, monkeypatch):
    """Chốt phải NGĂN đúng người, không được khoá luôn con đường hợp lệ."""
    monkeypatch.setattr(users_module, 'UserRepository', lambda: _Repo('super_admin'))
    _sign_in(client, 'super_admin')
    response = client.post('/api/users/10/reset-password',
                           json={'password': 'Legit12345', 'must_change_password': False})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert _Repo.calls == [(10, False)]


def test_admin_can_still_reset_an_ordinary_account(client, monkeypatch):
    """Không được biến bản vá thành một lần siết quyền ngoài ý muốn: đặt lại
    mật khẩu cho tài khoản thường vẫn là việc hằng ngày của admin."""
    monkeypatch.setattr(users_module, 'UserRepository', lambda: _Repo('operator'))
    _sign_in(client, 'admin')
    response = client.post('/api/users/10/reset-password',
                           json={'password': 'Normal12345', 'must_change_password': True})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert _Repo.calls == [(10, True)]


def test_the_guard_matches_the_two_sibling_routes():
    """Ba chốt phải cùng một hình dạng -- lệch nhau là cách chỗ này hổng lần đầu."""
    source = (users_module.__file__ and open(users_module.__file__, encoding='utf-8').read())
    assert source.count("_acting_role() != 'super_admin'") == 3, \
        'create/update/reset-password phải cùng dùng đúng một chốt'
