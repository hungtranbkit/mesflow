"""Một sự kiện offline phải tìm lại đúng Operation, kể cả sau khi mã đã đổi.

Đường offline là đường nguy hiểm nhất trong hệ thống về mặt danh tính, vì hai
lý do cộng lại: sự kiện nằm trong hàng đợi của thiết bị hàng giờ (thừa thời
gian để mã bị đổi tên ở trên server), và cả lô được áp dụng hàng loạt lúc đồng
bộ, không có ai đứng nhìn từng cái.

Ba trạng thái phải phân biệt rõ:

  * Thiết bị gửi kèm ``operation_id`` -> dùng id, không bao giờ mơ hồ.
  * Thiết bị chỉ gửi tem cũ, và tem đó vẫn giải ra duy nhất -> chạy bình
    thường. ``operations.qr`` CỐ Ý không bị viết lại khi đổi mã, nên chính điều
    đó giữ cho tem đã in (và bản chụp catalog trong máy) tiếp tục đúng.
  * Thiết bị chỉ gửi tem cũ, và tem đó đã hoá mơ hồ -> TỪ CHỐI TƯỜNG MINH, giữ
    sự kiện lại. Không bao giờ đoán.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


@pytest.fixture
def offline_graph(db):
    suffix = uuid.uuid4().hex[:8].upper()
    kiosk = f'OFF-ID-{suffix}'
    token = f'TEST-KIOSK-TOKEN-{suffix}'
    ids = {'suffix': suffix, 'kiosk': kiosk, 'token': token,
           'station_code': f'ST-OFF-{suffix}', 'op_code': f'OPOFF-{suffix}'}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-OFF-{suffix}',))
        ids['po_id'] = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,%s,'Part',0) RETURNING id",
                    (ids['po_id'], f'PART-{suffix}'))
        ids['part_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Công đoạn','IN_PROGRESS',%s,0) RETURNING id""",
            (ids['po_id'], ids['part_id'], ids['op_code'], f"WF|OP|{ids['op_code']}"))
        ids['op_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Công nhân','TEST','Worker',%s,true) RETURNING id""",
            (f'EOFF-{suffix}', f'WF|EMP|EOFF-{suffix}'))
        ids['employee_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO stations(code,name,workshop,production_line)
            VALUES(%s,'Trạm offline','TEST','TEST') RETURNING id""", (ids['station_code'],))
        ids['station_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
            VALUES(%s,'Kiosk offline','ACTIVE',%s,CURRENT_TIMESTAMP)""",
            (kiosk, hashlib.sha256(token.encode()).hexdigest()))
    yield ids
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_client_events WHERE kiosk_id=%s", (kiosk,))
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid=%s", (kiosk,))
        cur.execute("DELETE FROM kiosk_events WHERE operation_id=%s", (ids['op_id'],))
        cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (ids['employee_id'],))
        cur.execute("DELETE FROM operations WHERE id=%s", (ids['op_id'],))
        cur.execute("DELETE FROM parts WHERE id=%s", (ids['part_id'],))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (ids['po_id'],))
        cur.execute("DELETE FROM stations WHERE id=%s", (ids['station_id'],))
        cur.execute("DELETE FROM employees WHERE id=%s", (ids['employee_id'],))


def _event(graph, sequence, **overrides):
    event = {
        'schema_version': 1,
        'client_event_id': f"{graph['kiosk']}-{sequence:06d}",
        'local_sequence': sequence,
        'local_session_id': f"LOCAL-{graph['suffix']}-{sequence}",
        'session_trace_id': f"LOCAL-{graph['suffix']}-{sequence}",
        'event_type': 'START',
        'worker_qr': f"WF|EMP|EOFF-{graph['suffix']}",
        'operation_qr': f"WF|OP|{graph['op_code']}",
        'good_qty': 0, 'defect_qty': 0, 'repairable_qty': 0, 'scrap_qty': 0,
        'time_quality': 'unknown', 'boot_id': 'TEST-BOOT',
        'device_uptime_ms': sequence * 100,
        'offline_snapshot_revision': 'TEST-REVISION', 'offline': True,
    }
    event.update(overrides)
    return event


def _post(api, graph, events):
    return api.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
        'device_id': graph['kiosk'], 'station_code': graph['station_code'], 'events': events,
    }, timeout=30)


def test_snapshot_carries_the_immutable_id_alongside_the_legacy_fields(api, offline_graph):
    """Bản chụp catalog phải mang id, mà KHÔNG bỏ code/qr mà firmware v1 đang đọc.

    Firmware v1 phân tích JSON này qua một DeserializationOption::Filter liệt
    kê đích danh khoá nó giữ, nên khoá lạ bị vứt ngay trong lúc phân tích --
    thêm `id` không thể làm tràn tài liệu của nó.
    """
    graph = offline_graph
    response = api.get(f'{BASE_URL}/api/kiosk/offline-snapshot',
                       headers={'X-Device-ID': graph['kiosk']}, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    operations = body['operations']
    mine = [o for o in operations if o.get('code') == graph['op_code']]
    assert mine, f"không thấy Operation trong snapshot: {[o.get('code') for o in operations][:10]}"
    row = mine[0]
    assert int(row['id']) == graph['op_id'], row
    # Những khoá firmware v1 đang đọc phải còn nguyên.
    for key in ('code', 'name', 'qr', 'po', 'part'):
        assert key in row, f'snapshot thiếu khoá {key} mà firmware v1 đang đọc: {row}'
    employees = body['employees']
    assert all('id' in e for e in employees), 'snapshot nhân viên thiếu id'
    for key in ('employee_no', 'name', 'qr'):
        assert key in employees[0], f'snapshot nhân viên thiếu khoá {key}'


def test_an_event_carrying_operation_id_maps_by_id_even_after_a_rename(api, db, offline_graph):
    """Đây là điều mà việc thêm id vào snapshot mở ra.

    Sự kiện nằm trong hàng đợi, mã bị đổi tên ở server, rồi mới đồng bộ. Với
    id thì không có gì để mơ hồ.
    """
    graph = offline_graph
    with db.cursor() as cur:
        cur.execute("UPDATE operations SET code=%s WHERE id=%s",
                    (f"{graph['op_code']}-RENAMED", graph['op_id']))

    response = _post(api, graph, [_event(graph, 1,
                                         operation_id=graph['op_id'],
                                         employee_id=graph['employee_id'],
                                         operation_qr='WF|OP|KHONG-CON-TON-TAI')])
    assert response.status_code == 200, response.text
    with db.cursor() as cur:
        cur.execute("""SELECT ws.operation_id,ws.employee_id FROM work_sessions ws
            WHERE ws.operation_id=%s""", (graph['op_id'],))
        session = cur.fetchone()
    assert session, f'không mở được session bằng id: {response.text[:300]}'
    assert session['employee_id'] == graph['employee_id']


def test_a_legacy_payload_queued_before_a_rename_still_maps_after_it(api, db, offline_graph):
    """Tem cũ vẫn đúng sau khi đổi mã -- vì operations.qr cố ý không bị viết lại.

    Đây là lý do việc KHÔNG đồng bộ lại qr khi đổi mã là một quyết định, không
    phải một thiếu sót: nó giữ cho cả tem đã in ngoài xưởng lẫn bản chụp
    catalog trong máy tiếp tục trỏ đúng.
    """
    graph = offline_graph
    with db.cursor() as cur:
        cur.execute("UPDATE operations SET code=%s WHERE id=%s",
                    (f"{graph['op_code']}-RENAMED", graph['op_id']))

    response = _post(api, graph, [_event(graph, 2)])
    assert response.status_code == 200, response.text
    with db.cursor() as cur:
        cur.execute("SELECT operation_id FROM work_sessions WHERE operation_id=%s", (graph['op_id'],))
        assert cur.fetchone(), f'tem cũ không còn giải được sau khi đổi mã: {response.text[:300]}'


def test_a_bogus_operation_id_is_rejected_and_never_silently_falls_back(api, db, offline_graph):
    """id rác không được âm thầm rơi về giải theo chuỗi rồi mở nhầm session."""
    graph = offline_graph
    response = _post(api, graph, [_event(graph, 3, operation_id=99999999)])
    assert response.status_code == 200, response.text
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s", (graph['op_id'],))
        assert cur.fetchone()['n'] == 0, 'id rác đã rơi về tem cũ và mở session'
        cur.execute("SELECT status FROM kiosk_client_events WHERE client_event_id=%s",
                    (f"{graph['kiosk']}-000003",))
        row = cur.fetchone()
    assert row and row['status'] != 'accepted', row


def test_a_zero_or_empty_operation_id_falls_back_to_the_legacy_payload(api, db, offline_graph):
    """0 / '' / rác không phải id -- phải rơi về tem cũ, không thành id nào đó."""
    graph = offline_graph
    response = _post(api, graph, [_event(graph, 4, operation_id=0, employee_id='')])
    assert response.status_code == 200, response.text
    with db.cursor() as cur:
        cur.execute("SELECT operation_id FROM work_sessions WHERE operation_id=%s", (graph['op_id'],))
        assert cur.fetchone(), f'không rơi về tem cũ: {response.text[:300]}'
