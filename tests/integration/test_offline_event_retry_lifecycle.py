"""Sự kiện kiosk offline hỏng một lần không được mất vĩnh viễn.

VẤN ĐỀ. kiosk_client_events.status chỉ có 'accepted' / 'duplicate' /
'rejected'. Mọi lỗi nghiệp vụ -- kể cả loại chỉ TẠM thời đúng, như "OP nguồn
chưa có sản lượng để cấp" -- đều thành 'rejected', là trạng thái cuối. Thiết bị
nhận 'rejected' thì bỏ sự kiện. Một ca làm việc CÓ THẬT, ghi ở kiosk lúc mất
mạng, biến mất chỉ vì lúc đồng bộ thì công đoạn phía trước chưa kịp nhập số.

Chiều ngược lại cũng hở: lỗi hạ tầng trả 'transient' và cố ý KHÔNG ghi dòng
nào. Đúng cho thiết bị (nó giữ và gửi lại), nhưng máy chủ không còn dấu vết --
không ai biết có bao nhiêu sự kiện đang kẹt.

VÒNG ĐỜI SAU BẢN VÁ (migration 0049):

    PROCESSING -> accepted | duplicate | retryable | rejected

'retryable' KHÔNG phải trạng thái cuối: máy chủ giữ dòng kèm lý do và
attempt_count, còn thiết bị vẫn nhận 'transient' -- đúng thứ firmware hiện tại
đã hiểu là "giữ lại, gửi lại". Không đổi ESP. Quá MAX_RETRY_ATTEMPTS thì
chuyển 'rejected' với reason_code='RETRY_EXHAUSTED': dừng, nhưng dừng một cách
nhìn thấy được.

Phân loại cố ý nghiêng về "thử lại được": đoán sai theo hướng đó chỉ tốn vài
lần gửi lại; đoán sai theo hướng kia thì mất dữ liệu sản xuất.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

SYNC_URL = f'{BASE_URL}/api/kiosk/offline-sync'


def _graph(db, suffix):
    """OP đích có giới hạn đầu vào nhưng OP nguồn CHƯA sản xuất gì.

    Đây chính là hình dạng sinh ra ConflictError tạm thời: hôm nay chưa cấp
    được, ngày mai công đoạn trước nhập số thì cấp được.
    """
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-OFF-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'OP nguồn','PLANNED',%s,0) RETURNING id""",
            (po_id, part_id, f'OFF-{suffix}-SRC', f'WF|OP|OFF-{suffix}-SRC'))
        src = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,
                input_flow_enabled,input_source_operation_id,input_source_kind)
            VALUES(%s,%s,%s,'OP đích','PLANNED',%s,1,TRUE,%s,'GOOD') RETURNING id""",
            (po_id, part_id, f'OFF-{suffix}-DST', f'WF|OP|OFF-{suffix}-DST', src))
        dst = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ offline',%s,TRUE) RETURNING id""",
            (f'EMP-OFF-{suffix}', f'WF|EMP|EMP-OFF-{suffix}'))
        emp = cur.fetchone()
        # Nhân viên thứ hai để làm việc ở OP nguồn: dùng chung một người sẽ bị
        # chặn vì trùng giờ với session offline, che mất thứ đang muốn kiểm.
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ nguồn',%s,TRUE) RETURNING id""",
            (f'EMP-SRC-{suffix}', f'WF|EMP|EMP-SRC-{suffix}'))
        emp_src = cur.fetchone()
        cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,status)
            VALUES(%s,'Kiosk offline','ACTIVE')
            ON CONFLICT(device_uuid) DO UPDATE SET status='ACTIVE' RETURNING device_uuid""",
            (f'KIOSK-OFF-{suffix}',))
        kiosk = cur.fetchone()['device_uuid']
    return {'po_id': po_id, 'src': src, 'dst': dst, 'employee_no': f'EMP-OFF-{suffix}',
            'employee_id': emp['id'], 'employee_src_id': emp_src['id'], 'kiosk': kiosk,
            'src_code': f'OFF-{suffix}-SRC', 'dst_code': f'OFF-{suffix}-DST'}


def _drop(db, g):
    with db.cursor() as cur:
        cur.execute('DELETE FROM kiosk_client_events WHERE kiosk_id=%s', (g['kiosk'],))
        cur.execute("""DELETE FROM operation_input_consumptions WHERE session_id IN
            (SELECT id FROM work_sessions WHERE operation_id IN
             (SELECT id FROM operations WHERE production_order_id=%s))""", (g['po_id'],))
        cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
        cur.execute('DELETE FROM employees WHERE id IN (%s,%s)',
                    (g['employee_id'], g['employee_src_id']))
        cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (g['kiosk'],))


def _row(db, event_id):
    return db.execute("""SELECT status,reason_code,reason,attempt_count
        FROM kiosk_client_events WHERE client_event_id=%s""", (event_id,)).fetchone()


def _send(api, g, events):
    return api.post(SYNC_URL, json={'device_uuid': g['kiosk'], 'events': events}, timeout=25)


def _start_event(g, seq, event_id, employee_qr=None, operation_qr=None, local_session=None):
    """START offline, đúng hình dạng firmware gửi: định danh bằng QR."""
    return {
        'client_event_id': event_id, 'local_sequence': seq, 'event_type': 'START',
        'employee_qr': employee_qr or f"WF|EMP|{g['employee_no']}",
        'operation_qr': operation_qr or f"WF|OP|{g['dst_code']}",
        'time_quality': 'synced', 'event_time': '2026-08-21T01:00:00Z',
        'local_session_id': local_session or f'LS-{seq}',
    }


def _finish_event(g, seq, event_id, local_session=None, good=5):
    """FINISH offline. Nó nối về START qua local_session_id, nên bài test phải
    gửi START trước -- đúng như thiết bị làm."""
    return {
        'client_event_id': event_id, 'local_sequence': seq, 'event_type': 'FINISH',
        'good_qty': good, 'defect_qty': 0, 'rework_qty': 0,
        'time_quality': 'synced', 'event_time': '2026-08-21T02:00:00Z',
        'local_session_id': local_session or f'LS-{seq}',
    }


def test_a_temporarily_impossible_event_is_kept_for_retry_not_thrown_away(db, api):
    """OP nguồn chưa có hàng: hôm nay chưa cấp được, mai thì được."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    event_id = f'EVT-{suffix}-1'
    try:
        start_id = f'{event_id}-S'
        _send(api, g, [_start_event(g, 1, start_id)])
        response = _send(api, g, [_finish_event(g, 2, event_id, local_session='LS-1')])
        assert response.status_code in (200, 207), response.text
        row = _row(db, event_id)
        assert row is not None, 'sự kiện hỏng phải để lại dấu vết ở máy chủ'
        assert row['status'] == 'retryable', (
            f"trạng thái {row['status']!r} là trạng thái cuối -- thiết bị sẽ bỏ sự kiện này")
        assert row['reason_code'] in ('RETRYABLE_CONFLICT', 'TEMPORARY_FAILURE'), row['reason_code']
        assert row['reason'], 'phải ghi lý do để người vận hành hiểu vì sao kẹt'

        # Thiết bị phải được bảo "giữ lại", tức là KHÔNG phải rejected.
        body = response.json()
        results = body.get('results') or body.get('events') or []
        if results:
            got = [r for r in results if r.get('client_event_id') == event_id]
            assert got and got[0].get('status') != 'rejected', got
    finally:
        _drop(db, g)


def test_permanently_invalid_input_is_rejected_immediately(db, api):
    """Mã nhân viên không tồn tại: thời gian không chữa được, đừng thử lại."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    event_id = f'EVT-{suffix}-BAD'
    try:
        response = _send(api, g, [_start_event(g, 1, event_id, employee_qr='WF|EMP|KHONG-TON-TAI')])
        assert response.status_code in (200, 207), response.text
        row = _row(db, event_id)
        assert row is not None
        assert row['status'] == 'rejected', (
            f"dữ liệu sai vĩnh viễn không nên để ở {row['status']!r} rồi thử lại mãi")
        assert row['reason_code'] == 'BUSINESS_REJECT', row['reason_code']
    finally:
        _drop(db, g)


def test_retrying_the_same_event_counts_attempts_and_eventually_stops(db, api):
    """Thử lại phải đếm được, và phải có điểm dừng nhìn thấy được."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    event_id = f'EVT-{suffix}-LOOP'
    try:
        # START vào OP đích khi OP nguồn chưa có hàng -- điều kiện tạm thời sai.
        for _ in range(10):
            _send(api, g, [_start_event(g, 1, event_id)])
        row = _row(db, event_id)
        assert row['attempt_count'] > 1, 'gửi lại cùng client_event_id phải tăng số lần thử'
        assert row['status'] == 'rejected', 'thử mãi không được thì phải dừng'
        assert row['reason_code'] == 'RETRY_EXHAUSTED', (
            f"dừng vì hết lượt phải phân biệt được với dữ liệu sai: {row['reason_code']}")
    finally:
        _drop(db, g)


def test_an_event_that_becomes_possible_later_is_applied_on_retry(db, api):
    """Đây là điểm cốt lõi: sự kiện kẹt hôm qua phải chạy được hôm nay.

    Trước bản vá, lần gửi đầu ghi 'rejected' -- trạng thái cuối -- nên thiết bị
    bỏ luôn sự kiện và ca làm việc đó biến mất. Nay nó ở 'retryable' và lần gửi
    sau, khi công đoạn trước đã nhập số, được áp dụng bình thường.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    event_id = f'EVT-{suffix}-LATER'
    try:
        _send(api, g, [_start_event(g, 1, event_id)])
        assert _row(db, event_id)['status'] == 'retryable'

        # Công đoạn trước nhập số -- điều kiện đã đủ.
        started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
            'request_id': f'OFF-S-{uuid.uuid4()}', 'employee_id': g['employee_src_id'],
            'operation_id': g['src']}, timeout=20)
        assert started.status_code == 201, started.text
        sid = started.json()['session']['id']
        done = api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
            'request_id': f'OFF-F-{uuid.uuid4()}', 'good_qty': 50,
            'defect_qty': 0, 'rework_qty': 0}, timeout=20)
        assert done.status_code == 200, done.text

        resp = _send(api, g, [_start_event(g, 1, event_id)])
        row = _row(db, event_id)
        assert row['status'] == 'accepted', (
            f"sự kiện đã đủ điều kiện mà vẫn ở {row['status']!r} -- công sức của ca đó mất. "
            f"lý do={row['reason']!r} mã={row['reason_code']!r} phản hồi={resp.text[:300]}")
    finally:
        _drop(db, g)


def test_an_applied_event_is_never_downgraded_by_a_later_replay(db, api):
    """Idempotency: gửi lại sự kiện đã áp dụng không được làm hỏng nó."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    event_id = f'EVT-{suffix}-OK'
    try:
        # OP nguồn không có giới hạn đầu vào, nên START vào đó luôn hợp lệ.
        _send(api, g, [_start_event(g, 1, event_id,
                                    operation_qr=f"WF|OP|{g['src_code']}")])
        first = _row(db, event_id)
        assert first['status'] == 'accepted', first

        before = db.execute('SELECT COUNT(*) c FROM work_sessions WHERE operation_id=%s',
                            (g['src'],)).fetchone()['c']
        for _ in range(3):
            _send(api, g, [_start_event(g, 1, event_id,
                                        operation_qr=f"WF|OP|{g['src_code']}")])
        after = db.execute('SELECT COUNT(*) c FROM work_sessions WHERE operation_id=%s',
                           (g['src'],)).fetchone()['c']
        assert after == before, 'gửi lại không được tạo thêm session'
        assert _row(db, event_id)['status'] == 'accepted', 'trạng thái đã áp dụng không được tụt hạng'
    finally:
        _drop(db, g)
