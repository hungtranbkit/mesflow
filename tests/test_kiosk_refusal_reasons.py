"""Kiosk web: a refusal must say WHICH refusal it is.

Second pass of the 2026-09-29 DEV kiosk P0. After the demo-scan fix, the demo
sequence employee -> OP reached /api/kiosk-web/start correctly, and DEV
refused it with 409 "Ngoài ca làm việc…" (06:00 ICT, DAY starts 08:00). But:

  * the backend labelled it SES-409 with the action "Quét lại thẻ nhân
    viên…" -- the same advice as the old SCN-003 bug;
  * kiosk.js collapsed EVERY 409 into "Công đoạn này hiện không thể bắt
    đầu", so outside-shift, PO-not-started, operation-closed and a real
    session conflict all looked identical on screen and in kiosk_status;
  * an inactive employee at /start came back as an English 400
    "employee inactive or missing", shown as "Dữ liệu quét … chưa hợp lệ".

Contract now: every classified refusal carries a machine-readable `reason`,
a specific `error_code` and a Vietnamese message/action; kiosk.js shows the
server's message whenever `reason` is present. Status codes are unchanged.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mesflow.web import app as app_module
from mesflow.web import kiosk as kiosk_module
from mesflow.core.working_calendar import DEFAULT_SHIFTS
from mesflow.db.repositories.base import ConflictError, RepositoryError

ROOT = Path(__file__).resolve().parents[1]
ICT = ZoneInfo('Asia/Ho_Chi_Minh')


@pytest.fixture
def client():
    app = app_module.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _body(exc):
    with app_module.create_app().test_request_context():
        response, status = kiosk_module._error(exc)
        return status, response.get_json()


# The exact strings the start/finish path raises today (execution.py,
# production_state.py) -- classification must hold for the real messages.
@pytest.mark.parametrize('message,code,reason', [
    ('PO 6126 chưa Start hoặc đang tạm dừng', 'PO-001', 'PO_NOT_STARTED'),
    ('Operation OP01 đang ở trạng thái COMPLETED, không thể bắt đầu phiên làm việc', 'OP-409', 'OPERATION_CLOSED'),
    ('Operation OP01 đã CANCELLED, không thể mở lại phiên làm việc', 'OP-409', 'OPERATION_CLOSED'),
    ('SỬA HÀNG là bàn sửa hàng, không Start bằng QR. Ghi nhận số sửa được / loại tại màn hình Hàng chờ sửa.', 'OP-409', 'REWORK_BENCH'),
    ('Operation chưa sẵn sàng để Start: NO_WIP; WIP=0', 'OP-409', 'NOT_READY'),
    ('OP nguồn OP01 chưa bắt đầu session. Phải start session OP nguồn trước khi start OP02.', 'DEP-409', 'DEPENDENCY'),
    ('OP nguồn đầu vào không hợp lệ', 'QTY-409', 'INPUT_QTY'),
    ('Nhân viên đang mở Operation này rồi. Quét lại tem Operation để nhập sản lượng và kết thúc.', 'SES-409', 'SESSION_OPEN'),
    ('Khoảng thời gian này trùng với phiên làm việc #7 (OP01). Hãy điều chỉnh giờ bắt đầu hoặc giờ kết thúc.', 'SES-409', 'SESSION_OPEN'),
    ('session already closed', 'SES-409', 'SESSION_CONFLICT'),
])
def test_every_conflict_carries_a_specific_code_and_reason(message, code, reason):
    status, body = _body(ConflictError(message))
    assert status == 409
    assert body['error'] == 'CONFLICT'
    assert (body['error_code'], body['reason']) == (code, reason)
    assert body['message'] == message
    assert body['action']


def test_outside_shift_is_its_own_refusal_not_a_session_conflict():
    status, body = _body(kiosk_module.OutsideShiftError('Ngoài ca làm việc.'))
    assert status == 409
    assert (body['error_code'], body['reason']) == ('SHF-409', 'OUTSIDE_SHIFT')
    # The old action told the worker to re-scan the badge -- exactly the
    # SCN-003 symptom the user reported. It must not come back.
    assert 'thẻ nhân viên' not in body['action']


def test_outside_shift_start_names_the_configured_shift_hours(client, monkeypatch):
    tuesday_early = datetime(2026, 9, 29, 6, 0, tzinfo=ICT)
    monkeypatch.setattr(kiosk_module, 'utc_now', lambda: tuesday_early, raising=False)
    monkeypatch.setattr(kiosk_module, 'get_work_shifts', lambda: DEFAULT_SHIFTS, raising=False)

    class MustNotInsert:
        def start(self, *_a, **_k):
            raise AssertionError('outside a shift, start() must not run')

    monkeypatch.setattr(kiosk_module, 'WorkSessionRepository', MustNotInsert)
    response = client.post('/api/kiosk-web/start', json={'employee_id': 28, 'operation_id': 4})
    body = response.get_json()
    assert response.status_code == 409
    assert body['reason'] == 'OUTSIDE_SHIFT'
    assert body['message'].startswith('Ngoài ca làm việc.')
    for shift in DEFAULT_SHIFTS:
        assert str(shift['anchor_start'])[:5] in body['message'], body['message']


def test_inside_a_shift_the_start_reaches_the_repository(client, monkeypatch):
    """The gate is unchanged: at 09:00 on a working day the start goes through."""
    tuesday_morning = datetime(2026, 9, 29, 9, 0, tzinfo=ICT)
    monkeypatch.setattr(kiosk_module, 'utc_now', lambda: tuesday_morning, raising=False)
    monkeypatch.setattr(kiosk_module, 'get_work_shifts', lambda: DEFAULT_SHIFTS, raising=False)
    calls = []

    class Recorder:
        def start(self, payload):
            calls.append(payload)
            return {'ok': True, 'session': {'id': 1, 'operation_id': payload['operation_id']}}

    monkeypatch.setattr(kiosk_module, 'WorkSessionRepository', Recorder)
    response = client.post('/api/kiosk-web/start', json={'employee_id': 28, 'operation_id': 4})
    assert response.status_code == 201
    assert calls and calls[0]['employee_id'] == 28


def test_inactive_employee_at_start_is_named_not_a_generic_400():
    status, body = _body(RepositoryError('employee inactive or missing'))
    assert status == 400                       # status unchanged
    assert (body['error_code'], body['reason']) == ('EMP-001', 'EMPLOYEE_INACTIVE')
    assert 'Nhân viên' in body['message']
    assert 'inactive' not in body['message']   # no English internals on screen


def test_unclassified_input_errors_keep_their_old_shape():
    status, body = _body(ValueError('Thiếu mã nhân viên. Quét lại từ đầu.'))
    assert status == 400
    assert body['error_code'] == 'REQ-400'
    assert 'reason' not in body


def test_kiosk_js_shows_the_server_reason_and_reports_it():
    js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    assert ("const serverReason = data.reason && data.message && status >= 400 && status < 500\n"
            "        && status !== 401 && status !== 403;") in js
    assert '? {message:data.message, action:data.action || workerError(data, status).action}' in js
    assert 'if (data.reason) error.reason = String(data.reason);' in js
    assert 'setError(error.message, error.code, error.action, error.reason);' in js
    assert "lastHeartbeatError = `${safeCode}${reason ? ` ${reason}` : ''}: ${message || ''}`" in js
    for code in ('SHF-409', 'OP-409'):
        assert f"'{code}':" in js
