"""Mặt quét CÔNG KHAI không được trả lại mã thẻ nhân viên.

LỖI THẬT (SEC-01/SEC-07, audit 2026-09-14). Chuỗi `employees.qr` là một THÔNG
TIN XÁC THỰC -- không phải suy đoán của bài này, mà là điều chính codebase đã
kết luận và đã hành động theo: `/api/kiosk-web/demo-data` bị khoá lại sau sự cố
2026-09-09 đúng vì nó "dumps the whole employee roster INCLUDING every badge QR
value, which is a credential". Ai cầm chuỗi đó thì nhận diện được thành người
đó ở bất kỳ trạm nào, và sản lượng ghi vào tên họ.

Nhưng hai endpoint ẩn danh vẫn trả lại đúng chuỗi ấy:

  * ``POST /api/kiosk-web/scan`` -- và bộ giải mã chấp nhận cả `employee_no`
    (`qr_identity.py`: ``upper(qr)=upper(%s) OR upper(employee_no)=upper(%s)``),
    nên không cần cầm thẻ: đoán "WF|EMP|NV002" là đủ.
  * ``GET /api/lookup?qr=...`` -- ẩn danh hoàn toàn, không cần cả device, và
    nginx còn phục vụ nó trên cổng 80 KHÔNG mã hoá.

Đo được trên 71.0.0.310, không cookie không token:

    POST /api/kiosk-web/scan {"qr":"WF|EMP|NV002"}
      -> {"employee": {..., "name": "Lê Văn Lý", "qr": "WF|EMP|NV002", ...}}

tức là dò NV001..NV999 thu về toàn bộ danh sách nhân sự KÈM thẻ của từng người.

Trạm quét không cần chuỗi đó: nó vừa tự đọc được từ tấm thẻ trên tay. Nên bỏ
khỏi phản hồi là mất mát bằng không.

Bài chạy in-process (create_app + test_client) và chặn ở tầng hàm, không cần
PostgreSQL.
"""
from __future__ import annotations

import pytest

from mesflow.web import kiosk as kiosk_module

BADGE = 'WF|EMP|NV001'

ROW = {
    'id': 7, 'employee_no': 'NV001', 'name': 'Huỳnh Thị Mơ', 'department': 'QUẢN LÝ',
    'position': 'Tổng Giám Đốc', 'active': True, 'employment_status': 'Đang làm',
    'qr': BADGE,
}


def test_the_public_shape_drops_the_badge_and_the_employment_status():
    out = kiosk_module._public_employee(ROW)
    assert 'qr' not in out
    assert 'employment_status' not in out


def test_it_keeps_everything_the_kiosk_screen_actually_shows():
    """Bịt chỗ rò mà không làm hỏng màn hình: tên, mã NV và bộ phận là ba thứ
    kiosk.js vẽ ra sau mỗi lần quét."""
    out = kiosk_module._public_employee(ROW)
    assert out['id'] == 7
    assert out['employee_no'] == 'NV001'
    assert out['name'] == 'Huỳnh Thị Mơ'
    assert out['department'] == 'QUẢN LÝ'
    assert out['position'] == 'Tổng Giám Đốc'
    assert out['active'] is True


def test_it_is_an_allow_list_so_a_new_column_cannot_leak_by_default():
    """Danh sách CHO PHÉP, không phải danh sách cấm. Thêm cột mới vào bảng
    employees (số CMND, lương, số điện thoại...) không được âm thầm đẩy nó ra
    internet chỉ vì không ai nhớ thêm vào danh sách cấm."""
    row = dict(ROW, national_id='0790000001', phone='0900000000', salary=42)
    out = kiosk_module._public_employee(row)
    assert set(out) <= set(kiosk_module.PUBLIC_EMPLOYEE_FIELDS)
    for leaked in ('national_id', 'phone', 'salary', 'qr'):
        assert leaked not in out


def test_the_badge_string_appears_nowhere_in_the_serialized_response():
    """Kiểm trên CHUỖI đã tuần tự hoá, không kiểm từng khoá -- kiểm từng khoá
    vẫn xanh khi chuỗi thẻ lọt ra qua một trường khác."""
    import json
    assert BADGE not in json.dumps(kiosk_module._public_employee(ROW), ensure_ascii=False)


def test_the_legacy_lookup_endpoint_stopped_returning_it_too():
    """/api/lookup là đường rò thứ hai, và là đường tệ hơn: ẩn danh hoàn toàn,
    chỉ cần một GET, và nginx phục vụ nó trên cổng 80 không mã hoá."""
    source = (__import__('pathlib').Path(__file__).resolve().parents[1]
              / 'app/mesflow/web/execution.py').read_text(encoding='utf-8')
    block = source[source.index("type='worker'"):]
    block = block[:block.index('\n')]
    assert "'qr'" not in block, f'/api/lookup vẫn trả mã thẻ: {block}'
    # ...và vẫn trả những thứ thiết bị cần để hiện tên người.
    for kept in ("'name'", "'employee_code'", "'code'"):
        assert kept in block


def test_demo_data_is_still_the_one_place_that_may_expose_badges():
    """Nó vẫn được phép -- nhưng chỉ vì nó đứng sau @login_required. Nếu ai đó
    gỡ chốt ấy ra thì bài này phải đỏ cùng."""
    source = (__import__('pathlib').Path(__file__).resolve().parents[1]
              / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    head = source[source.index("@bp.get('/api/kiosk-web/demo-data')"):]
    head = head[:head.index('def ')]
    assert '@login_required' in head
