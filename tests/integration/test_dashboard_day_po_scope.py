"""Dashboard theo ngày lọc được theo Production Order — REQ-DASH-006.

Phạm vi PO phải nằm TRONG truy vấn, không phải lọc ở trình duyệt sau khi server
đã cắt theo LIMIT. Đây đúng là lỗi đã sửa ở REQ-PO-005, chỉ đổi màn hình: cả ba
truy vấn của ngày (items / sessions / activity) đều có LIMIT, nên lọc sau khi
lấy về sẽ lọc trên phần đã bị cắt — một PO ít hoạt động ra rỗng dù dữ liệu vẫn
còn nguyên trong DB.

Bài test dựng hai PO cùng ngày rồi đòi hỏi: hỏi PO nào chỉ ra dữ liệu PO đó, và
không hỏi thì hành vi cũ không đổi.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


@pytest.fixture()
def two_day_orders(db):
    """Hai PO, mỗi PO một Operation có session đã đóng trong hôm nay."""
    suffix = uuid.uuid4().hex[:8].upper()
    made = {}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr)
            VALUES(%s,'Thợ Dash','TEST','Worker',%s) RETURNING id""",
            (f'DS-{suffix}', f'WF|EMP|DS-{suffix}'))
        employee_id = cur.fetchone()['id']
        for label, good in (('A', 11), ('B', 22)):
            cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
                VALUES(%s,%s,100,'IN_PROGRESS') RETURNING id""",
                (f'PO-DS{label}-{suffix}', f'SP {label}'))
            po_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,%s,%s,0,true) RETURNING id""",
                (po_id, f'PT-{label}-{suffix}', f'Thân {label}'))
            part_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,0) RETURNING id""",
                (po_id, part_id, f'DS-{label}-{suffix}', f'Công đoạn {label}',
                 f'WF|OP|DS-{label}-{suffix}'))
            op_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO work_sessions
                  (employee_id,operation_id,status,started_at,ended_at,good_qty,defect_qty,
                   rework_qty,scrap_qty,quantity_confirmed,start_request_id,finish_request_id)
                VALUES(%s,%s,'CLOSED',CURRENT_TIMESTAMP - INTERVAL '2 hours',
                       CURRENT_TIMESTAMP - INTERVAL '1 hour',%s,0,0,0,TRUE,%s,%s) RETURNING id""",
                (employee_id, op_id, good, f'DS-START-{label}-{suffix}', f'DS-FIN-{label}-{suffix}'))
            session_id = cur.fetchone()['id']
            made[label] = {'po_id': po_id, 'op_id': op_id, 'session_id': session_id,
                           'code': f'PO-DS{label}-{suffix}', 'good': good}
    made['employee_id'] = employee_id
    yield made
    with db.cursor() as cur:
        for label in ('A', 'B'):
            po_id = made[label]['po_id']
            cur.execute('DELETE FROM work_sessions WHERE operation_id IN (SELECT id FROM operations WHERE production_order_id=%s)', (po_id,))
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
        cur.execute('DELETE FROM employees WHERE id=%s', (employee_id,))


def _day(api, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    response = api.get(f'{BASE_URL}/api/dashboard/day?{query}', timeout=25)
    assert response.status_code == 200, response.text
    return response.json()


def test_items_are_scoped_to_the_requested_po(api, two_day_orders):
    """Tab "Tổng quan Operation" đọc `items`."""
    data = _day(api, po_id=two_day_orders['A']['po_id'], limit=1000)
    ids = {int(x['po_id']) for x in data['items']}
    assert ids == {two_day_orders['A']['po_id']}, f'lẫn PO khác: {ids}'


def test_sessions_are_scoped_to_the_requested_po(api, two_day_orders):
    """Tab "Nhân viên / Session" đọc `sessions`."""
    data = _day(api, po_id=two_day_orders['A']['po_id'], limit=1000)
    mine = [x for x in data['sessions'] if int(x['session_id']) in
            {two_day_orders['A']['session_id'], two_day_orders['B']['session_id']}]
    assert [int(x['session_id']) for x in mine] == [two_day_orders['A']['session_id']]
    assert all(int(x['po_id']) == two_day_orders['A']['po_id'] for x in data['sessions'])


def test_activity_is_scoped_to_the_requested_po(api, two_day_orders):
    """Dải "Diễn biến trong ngày" đọc `activity`."""
    data = _day(api, po_id=two_day_orders['A']['po_id'], limit=1000)
    codes = {x.get('po_code') for x in data['activity']}
    assert two_day_orders['B']['code'] not in codes


def test_the_two_orders_do_not_leak_into_each_other(api, two_day_orders):
    """Hỏi A rồi hỏi B phải ra hai tập rời nhau — cùng ngày, cùng nhân viên."""
    a = _day(api, po_id=two_day_orders['A']['po_id'], limit=1000)
    b = _day(api, po_id=two_day_orders['B']['po_id'], limit=1000)
    a_ops = {int(x['operation_id']) for x in a['items']}
    b_ops = {int(x['operation_id']) for x in b['items']}
    assert two_day_orders['A']['op_id'] in a_ops
    assert two_day_orders['B']['op_id'] in b_ops
    assert not (a_ops & b_ops)


def test_context_reports_which_po_is_in_scope(api, two_day_orders):
    """Màn hình phải đọc được phạm vi từ chính phản hồi, không tự nhớ."""
    scoped = _day(api, po_id=two_day_orders['A']['po_id'])
    assert int(scoped['context']['po_id']) == two_day_orders['A']['po_id']
    everything = _day(api, limit=1000)
    assert everything['context']['po_id'] is None


def test_without_po_id_behaviour_is_unchanged(api, two_day_orders):
    """"Tất cả PO" là mặc định: nơi gọi cũ không truyền gì thì thấy cả hai."""
    data = _day(api, limit=2000)
    ops = {int(x['operation_id']) for x in data['items']}
    assert two_day_orders['A']['op_id'] in ops
    assert two_day_orders['B']['op_id'] in ops


def test_a_bad_po_id_is_refused_rather_than_ignored(api):
    """Làm ngơ tham số không hiểu = màn hình tưởng đã lọc mà đang đọc cả xưởng."""
    response = api.get(f'{BASE_URL}/api/dashboard/day?po_id=abc', timeout=25)
    assert response.status_code in {400, 422}, response.status_code


def test_an_unknown_po_returns_empty_not_everything(api, two_day_orders):
    """PO không tồn tại phải ra RỖNG, tuyệt đối không rơi về 'tất cả'.

    Rơi về 'tất cả' là kiểu hỏng im lặng tệ nhất cho một bộ lọc: người dùng tin
    con số đang nói về PO họ chọn.
    """
    data = _day(api, po_id=999999999, limit=1000)
    assert data['items'] == []
    assert data['sessions'] == []
