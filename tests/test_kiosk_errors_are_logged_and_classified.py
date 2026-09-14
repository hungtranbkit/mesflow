"""Lỗi trên đường ghi của kiosk: nói tiếng người, và KHÔNG được biến mất.

LỖI THẬT (DB-07 + ERR-01, audit 2026-09-14). `_error()` trong web/kiosk.py là
một bản sao yếu hơn của trình xử lý lỗi chung: nó BẮT ngoại lệ, KHÔNG ghi log,
và xếp `KeyError`/`TypeError` -- vốn là LỖI LẬP TRÌNH -- vào HTTP 400 kèm
nguyên văn nội dung ngoại lệ Python.

Hai hậu quả, đo được trên 71.0.0.310 với người gọi ẨN DANH:

    POST /api/kiosk-web/start {}                    -> 400  "'employee_id'"
    POST /api/kiosk-web/start {"employee_id":"abc"} -> 400  "invalid literal
                                                             for int() with base 10: 'abc'"

  1. Nội bộ Python lọt ra internet, và người đứng máy đọc được một câu Python
     thay vì một hướng dẫn.
  2. Tệ hơn: LỖI THẬT BIẾN MẤT. action_logging chỉ ghi `error_traces` khi
     ``status>=500`` hoặc có ngoại lệ chưa bắt. Vì đã bắt và trả 400 nên sau cả
     ba lời gọi trên ``SELECT count(*) FROM error_traces`` = **0**, và
     `outcome` là 'FAILED' chứ không phải 'ERROR'. Một defect thật không bao
     giờ tới được màn Nhật ký lỗi mà cả System Console dựng lên để theo dõi --
     trên chính đường ghi đông nhất và quan trọng nhất của hệ thống.

Bản vá phải đạt CẢ HAI, và đó là lý do có hai nhóm bài dưới đây: thiếu trường
vẫn là 400 với câu tiếng Việt đọc được, còn lỗi lập trình thì thành 500 và
được GHI LẠI.
"""
from __future__ import annotations

import logging

import pytest

from mesflow.web import app as app_module
from mesflow.web import kiosk as kiosk_module


@pytest.fixture
def client():
    app = app_module.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


# --- 1. Người dùng gửi thiếu/sai: vẫn 400, và câu chữ phải đọc được ---------
@pytest.mark.parametrize('body,expect', [
    ({}, 'Thiếu mã nhân viên'),
    ({'employee_id': 1}, 'Thiếu mã công đoạn'),
    ({'employee_id': None, 'operation_id': None}, 'Thiếu mã nhân viên'),
    ({'employee_id': 'abc', 'operation_id': 1}, 'mã nhân viên không hợp lệ'),
    ({'employee_id': 1, 'operation_id': 'xyz'}, 'mã công đoạn không hợp lệ'),
])
def test_a_missing_or_bad_field_is_a_readable_400(client, body, expect):
    response = client.post('/api/kiosk-web/start', json=body)
    assert response.status_code == 400
    assert expect in response.get_json()['message']


@pytest.mark.parametrize('body', [
    {}, {'employee_id': 'abc', 'operation_id': 1}, {'employee_id': None, 'operation_id': None},
])
def test_no_python_internals_reach_an_anonymous_caller(client, body):
    """Mặt này công khai trên internet. Không câu nào được lộ nội bộ."""
    message = client.post('/api/kiosk-web/start', json=body).get_json()['message']
    for leak in ('invalid literal', 'NoneType', 'int()', 'Traceback',
                 'base 10', "'employee_id'", 'KeyError', 'TypeError'):
        assert leak not in message, f'lộ nội bộ Python: {message!r}'


# --- 2. Lỗi lập trình: 500, và PHẢI được ghi lại ---------------------------
def test_a_programming_bug_becomes_500_and_is_logged(client, monkeypatch, caplog):
    """Trước bản vá đây là một 400 im lặng -- không log, không error_traces.

    Dùng TypeError vì đó chính là loại từng bị xếp nhầm vào 400.
    """
    def boom(*args, **kwargs):
        raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")
    monkeypatch.setattr(kiosk_module, 'WorkSessionRepository', boom)

    with caplog.at_level(logging.ERROR, logger='mesflow.web.kiosk'):
        response = client.post('/api/kiosk-web/start',
                               json={'employee_id': 1, 'operation_id': 2})

    assert response.status_code == 500, 'lỗi lập trình phải là 500, không phải 400'
    body = response.get_json()
    assert body['error_code'] == 'SYS-500'
    # Câu cho người dùng vẫn là câu chung -- không lộ nội bộ...
    assert 'unsupported operand' not in body['message']
    # ...nhưng traceback thì phải có trong log.
    assert caplog.records, 'không ghi lại gì cả -- đúng lỗi cũ'
    assert any(r.exc_info for r in caplog.records), 'thiếu traceback'
    assert any('unsupported operand' in r.exc_text for r in caplog.records if r.exc_text)


def test_key_error_is_no_longer_advertised_as_a_client_error():
    """Chốt lại ở mức mã nguồn: KeyError/TypeError không được nằm ở nhánh 400."""
    source = (__import__('pathlib').Path(__file__).resolve().parents[1]
              / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    branch = source[source.index('def _error('):source.index("error_code='SYS-500'")]
    # Bỏ chú thích trước khi tìm: chính đoạn chú thích giải thích vì sao
    # KeyError bị loại lại chứa đúng cái từ mà bài này cấm xuất hiện trong MÃ.
    code = '\n'.join(x for x in branch.splitlines() if not x.lstrip().startswith('#'))
    isinstance_lines = [x for x in code.splitlines() if 'isinstance' in x]
    assert not any('KeyError' in x for x in isinstance_lines), isinstance_lines
    four_hundred = [x for x in isinstance_lines
                    if 'ValueError' in x or 'RepositoryError' in x]
    assert four_hundred, 'nhánh 400 biến mất hẳn -- không phải điều bản vá muốn'
    assert not any('TypeError' in x for x in four_hundred), four_hundred


# --- 3. Những phân loại ĐÚNG sẵn có không được đổi -------------------------
def test_business_errors_keep_their_codes(client, monkeypatch):
    """Bản vá chỉ đụng KeyError/TypeError; 404/409/403 giữ nguyên hợp đồng."""
    from mesflow.db.repositories.base import ConflictError, NotFoundError
    from mesflow.domain.errors import PermissionDeniedError
    for exc, status, code in (
        (NotFoundError('session not found'), 404, 'DAT-404'),
        (ConflictError('session already closed'), 409, 'SES-409'),
        (PermissionDeniedError('kiosk disabled'), 403, 'AUTH-403'),
        (ValueError('qr không hợp lệ'), 400, 'REQ-400'),
    ):
        with app_module.create_app().test_request_context():
            response, got = kiosk_module._error(exc)
            assert got == status, (exc, got)
            assert response.get_json()['error_code'] == code
