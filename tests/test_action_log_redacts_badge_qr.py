"""Mã QR thẻ nhân viên KHÔNG được nằm nguyên văn trong action_logs.

Chuỗi `WF|EMP|<...>` là một THÔNG TIN XÁC THỰC, không phải một mã tra cứu vô
hại -- chính codebase này nói thế: `/api/kiosk-web/demo-data` bị khoá lại
(2026-09-09) đúng vì nó "dumps the whole employee roster INCLUDING every badge
QR value, which is a credential". Ai cầm chuỗi đó thì nhận diện được thành
người đó ở bất kỳ trạm nào.

Bản vá này chặn một chỗ rò ÂM THẦM hơn nhiều so với endpoint kia. Đo được trên
71.0.0.310 trước khi sửa, bằng một lần quét ẩn danh trên mặt kiosk công khai:

    POST /api/kiosk-web/scan {"qr": "WF|EMP|NV001"}
    -> action_logs.request_json  = {"qr": "WF|EMP|NV001"}
       action_logs.response_json = {"employee": {..., "qr": "WF|EMP|NV001", ...}}

tức là mỗi lần công nhân quét thẻ, hệ thống lại chép thêm một bản thẻ của họ vào
cơ sở dữ liệu -- giữ 30 ngày (log_retention_success_days), nằm trong mọi bản
backup, và mọi admin đọc được qua /api/system/action-logs/<id>.

Bài này kiểm ĐÚNG hàm đang che (`_clean`/`_json`), không cần PostgreSQL: đó là
nơi luật che được định nghĩa, và cũng là nơi một lần sửa danh sách khoá sau này
có thể vô tình gỡ nó ra.
"""
from __future__ import annotations

import json

import pytest

from mesflow.web import action_logging

BADGE = 'WF|EMP|NV001'
OP_QR = 'WF|OPID|4242'

#: Đúng thân yêu cầu và thân phản hồi của một lần quét thẻ thật.
SCAN_REQUEST = {'qr': BADGE}
SCAN_RESPONSE = {
    'ok': True, 'type': 'employee',
    'employee': {'id': 1, 'employee_no': 'NV001', 'name': 'Huỳnh Thị Mơ',
                 'department': 'QUẢN LÝ', 'position': 'Tổng Giám Đốc',
                 'active': True, 'qr': BADGE},
    'open_session': None,
}


def test_badge_qr_never_reaches_the_log_verbatim():
    """Kiểm trên CHUỖI đã tuần tự hoá, không kiểm từng khoá.

    Kiểm từng khoá sẽ xanh ngay cả khi chuỗi thẻ lọt ra qua một khoá khác
    (lồng trong danh sách, trong một trường phụ, trong bản sao nào đó) -- mà
    đó mới đúng là kiểu rò cần chặn.
    """
    for payload in (SCAN_REQUEST, SCAN_RESPONSE):
        dumped = action_logging._json(payload)
        assert BADGE not in dumped, f'chuỗi thẻ lọt vào nhật ký: {dumped}'
        assert '***' in dumped, f'không thấy dấu đã che trong: {dumped}'


def test_the_rest_of_the_scan_is_still_logged():
    """Che thẻ, KHÔNG che khả năng lần vết.

    Một bản vá che sạch cả bản ghi thì cũng làm hỏng nhật ký. Cái còn lại phải
    đủ để trả lời "ai, việc gì, lúc nào": mã nhân viên, tên, bộ phận, id.
    """
    dumped = json.loads(action_logging._json(SCAN_RESPONSE))
    employee = dumped['employee']
    assert employee['employee_no'] == 'NV001'
    assert employee['name'] == 'Huỳnh Thị Mơ'
    assert employee['id'] == 1
    assert employee['qr'] == '***'


def test_operation_qr_is_covered_too():
    """Tem công đoạn đi qua đúng một đường ghi nhật ký với thẻ nhân viên."""
    assert OP_QR not in action_logging._json({'qr': OP_QR})


def test_a_nested_or_renamed_qr_field_is_covered():
    """Luật che theo TÊN KHOÁ, nên phải phủ cả các tên phái sinh và lồng nhau."""
    payload = {'operations': [{'operation_qr': OP_QR, 'code': 'OP01'}],
               'employees': [{'qr': BADGE, 'employee_no': 'NV001'}]}
    dumped = action_logging._json(payload)
    assert BADGE not in dumped and OP_QR not in dumped, dumped
    # ...và phần không nhạy cảm vẫn còn.
    assert 'OP01' in dumped and 'NV001' in dumped


def test_passwords_are_still_redacted():
    """Bảo vệ cũ không được mất khi thêm khoá mới vào danh sách."""
    dumped = action_logging._json({'username': 'admin', 'password': 'Secret123!'})
    assert 'Secret123!' not in dumped
    assert 'admin' in dumped


@pytest.mark.parametrize('key', ['password', 'token', 'authorization', 'cookie',
                                 'secret', 'api_key', 'qr'])
def test_the_redaction_list_is_the_documented_one(key):
    """Danh sách khoá là hợp đồng, không phải chi tiết cài đặt: gỡ một mục ra
    là mở lại một chỗ rò, nên việc gỡ phải làm đỏ một bài kiểm."""
    assert key in action_logging.SENSITIVE
