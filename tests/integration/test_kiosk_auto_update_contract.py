"""Hợp đồng phía máy chủ của cơ chế kiosk tự nạp bản mới, và tương thích ngược
cho firmware ESP legacy sau migration 0054.

HAI THỨ Ở ĐÂY KHÔNG LIÊN QUAN NHAU VỀ TÍNH NĂNG nhưng cùng một rủi ro: cả hai
đều là thứ chỉ hỏng ở NGOÀI XƯỞNG, trên thiết bị không ai với tới được, và
không hỏng ở máy người phát triển.
"""
import uuid

import pytest

pytestmark = pytest.mark.postgres

BASE = 'http://mesflow-test-api:8080'


def _no_store(headers):
    value = (headers.get('Cache-Control') or '').lower()
    return 'no-store' in value


def test_kiosk_page_is_never_cached(api):
    """Tài liệu kiosk mang các con trỏ `?v=<version>` cho JS/CSS.

    Nếu CHÍNH nó nằm lại trong cache thì kiosk vĩnh viễn nạp bộ asset cũ, dù đã
    deploy bao nhiêu lần -- và vì `?v=` trong bản HTML cũ cũng cũ, không có gì
    buộc trình duyệt phải tải lại. Trang này trước đây trả về không kèm một
    header cache nào, tức là phó mặc cho phép đoán tự do của trình duyệt/proxy.
    """
    response = api.get(f'{BASE}/kiosk', timeout=15)
    assert response.status_code == 200, response.text
    assert _no_store(response.headers), dict(response.headers)


def test_kiosk_health_reports_version_and_is_never_cached(api):
    """Khai báo phiên bản bị cache thì nói mãi một con số cũ -- nói dối đúng về
    thứ nó tồn tại để trả lời."""
    response = api.get(f'{BASE}/api/kiosk-web/health', timeout=15)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ok'] is True
    assert body['version'], body
    assert _no_store(response.headers), dict(response.headers)


def test_heartbeat_reports_server_version(api, seeded_factory):
    """Đây là nhịp mà kiosk.js đối chiếu để phát hiện deploy. Mất trường
    `version` là cơ chế tự cập nhật im lặng ngừng hoạt động -- không lỗi, không
    dấu hiệu, chỉ là máy ngoài xưởng không bao giờ mới nữa."""
    response = api.post(f'{BASE}/api/kiosk-web/heartbeat',
                        json={'device_uuid': f'WEB-AUTOUPD-{uuid.uuid4().hex[:8]}',
                              'device_name': 'Web Kiosk Test'}, timeout=15)
    assert response.status_code == 200, response.text
    assert response.json()['version'], response.text


def _extra_operation(db, g, tag):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                       VALUES(%s,%s,%s,'ESP compat op','IN_PROGRESS',%s) RETURNING id""",
                    (g['po_id'], g['part_id'], f"TEST-OP-{g['suffix']}-{tag}",
                     f"WF|OP|TEST-OP-{g['suffix']}-{tag}"))
        return cur.fetchone()['id']


def test_legacy_lookup_returns_every_open_session(db, api, seeded_factory):
    """T14/smoke: /api/lookup là endpoint firmware ESP legacy gọi khi quét thẻ.

    Trước migration 0054 `active_sessions` là mảng nhưng NHIỀU NHẤT một phần tử,
    vì một người chỉ được một session OPEN. Nay nó có thể có nhiều -- hình dạng
    phản hồi KHÔNG đổi (vẫn là mảng, vẫn cùng tên trường), nên firmware cũ không
    phải sửa gì; nhưng nó phải thật sự trả về đủ, chứ không cắt còn một.

    Bài này chốt đúng điều đó ở mức smoke. Việc firmware xử lý mảng nhiều phần
    tử ra sao nằm ngoài tầm với của máy chủ và được ghi lại như giới hạn còn lại.
    """
    g = seeded_factory
    op_b = _extra_operation(db, g, 'ESPB')
    for operation_id in (g['operation_id'], op_b):
        r = api.post(f'{BASE}/api/work-sessions/start', json={
            'request_id': f'esp-{uuid.uuid4()}', 'employee_id': g['employee_id'],
            'operation_id': operation_id, 'station_id': g['station_id'], 'device_uuid': 'esp-compat',
        }, timeout=15)
        assert r.status_code == 201, r.text

    with db.cursor() as cur:
        cur.execute('SELECT qr FROM employees WHERE id=%s', (g['employee_id'],))
        employee_qr = cur.fetchone()['qr']

    response = api.get(f'{BASE}/api/lookup', params={'qr': employee_qr}, timeout=15)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['type'] == 'worker', body
    active = body['active_sessions']
    assert isinstance(active, list), body
    assert len(active) == 2, active
    assert {int(x['operation_id']) for x in active} == {int(g['operation_id']), int(op_b)}
    # Hình dạng từng phần tử không đổi -- đây là phần firmware thật sự đọc.
    for item in active:
        assert {'id', 'operation_id', 'start_time'} <= set(item), item
    # KHÔNG trả lại chuỗi thẻ: endpoint này ẩn danh hoàn toàn (xem web/execution.py).
    assert 'qr' not in body['worker'], body['worker']
