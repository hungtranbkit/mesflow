"""V66 flagship migration: /api/work-sessions/start and
/api/work-sessions/<id>/finish now flow through
Route -> Typed Command -> SessionService -> Repository -> single transaction
-> transactional Audit -> Domain Event, instead of calling
WorkSessionRepository directly from the route. This test proves, against a
real PostgreSQL instance and a real running MESFlow API, that:

  - the external HTTP contract (status codes, response shape) is unchanged,
  - existing business rules (overlap guard, rework<=defect, double-finish
    rejection, idempotent replay) still hold through the new path,
  - the audit_logs row created for SESSION_STARTED/SESSION_FINISHED is
    transactionally consistent (exists exactly once per real mutation, not
    per idempotent replay) and carries the request's X-Trace-ID as its
    correlation_id, closing the HTTP -> service -> DB -> audit trace.
"""
import uuid

import pytest

pytestmark = pytest.mark.postgres

BASE = 'http://mesflow-test-api:8080'


def _start(api, g, request_id=None, trace_id=None, operation_id=None):
    headers = {'X-Trace-ID': trace_id} if trace_id else {}
    return api.post(f'{BASE}/api/work-sessions/start', json={
        'request_id': request_id or f'v66-start-{uuid.uuid4()}',
        'employee_id': g['employee_id'],
        'operation_id': operation_id or g['operation_id'],
        'station_id': g['station_id'],
        'device_uuid': 'v66-test',
    }, headers=headers, timeout=10)


def _extra_operations(db, g, count):
    """Thêm Operation trên CÙNG Part/PO của fixture.

    Cùng PO là có chủ ý: đó là hình dạng thật ngoài xưởng (một người trông nhiều
    công đoạn của cùng một lô), và cũng là hình dạng chạm vào lock dòng PO trong
    start() -- nếu thứ tự khoá sai thì đây là chỗ nó lộ ra."""
    ids = []
    with db.cursor() as cur:
        for i in range(count):
            code = f"{g['suffix']}-EXTRA{i}"
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                           VALUES(%s,%s,%s,'Docker Test Operation extra','IN_PROGRESS',%s) RETURNING id""",
                        (g['po_id'], g['part_id'], f'TEST-OP-{code}', f'WF|OP|TEST-OP-{code}'))
            ids.append(cur.fetchone()['id'])
    return ids


def _finish(api, session_id, request_id=None, trace_id=None, **qty):
    headers = {'X-Trace-ID': trace_id} if trace_id else {}
    body = {'request_id': request_id or f'v66-finish-{uuid.uuid4()}', 'good_qty': 5, 'defect_qty': 0, 'rework_qty': 0}
    body.update(qty)
    return api.post(f'{BASE}/api/work-sessions/{session_id}/finish', json=body, headers=headers, timeout=10)


def test_start_then_finish_happy_path_has_unchanged_response_contract(db, api, seeded_factory):
    g = seeded_factory
    r = _start(api, g)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {'ok', 'session', 'idempotent_replay'}
    assert body['ok'] is True and body['idempotent_replay'] is False
    session_id = body['session']['id']

    r = _finish(api, session_id, good_qty=7, defect_qty=2, rework_qty=1)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {'ok', 'session', 'idempotent_replay'}
    assert body['session']['status'] == 'CLOSED'
    assert body['session']['good_qty'] == 7
    assert body['session']['defect_qty'] == 2
    assert body['session']['rework_qty'] == 1


def test_finish_creates_a_transactionally_consistent_audit_row_with_trace_id(db, api, seeded_factory):
    g = seeded_factory
    trace_id = f'trace-{uuid.uuid4()}'
    r = _start(api, g, trace_id=trace_id)
    assert r.status_code == 201, r.text
    session_id = r.json()['session']['id']

    r = _finish(api, session_id, trace_id=trace_id, good_qty=3, defect_qty=0, rework_qty=0)
    assert r.status_code == 200, r.text

    with db.cursor() as cur:
        cur.execute(
            "SELECT action,entity_type,entity_id,correlation_id,employee_id,after_json FROM audit_logs "
            "WHERE action='SESSION_FINISHED' AND entity_id=%s ORDER BY id DESC LIMIT 1",
            (str(session_id),),
        )
        row = cur.fetchone()
    assert row is not None, 'expected exactly one SESSION_FINISHED audit row for this session'
    assert row['entity_type'] == 'work_session'
    assert row['correlation_id'] == trace_id
    assert row['employee_id'] == g['employee_id']

    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM audit_logs WHERE action='SESSION_STARTED' AND entity_id=%s",
            (str(session_id),),
        )
        started_rows = cur.fetchall()
    assert len(started_rows) == 1, 'SESSION_STARTED must be audited exactly once, not on replay'


def test_idempotent_replay_does_not_duplicate_the_audit_row(db, api, seeded_factory):
    g = seeded_factory
    request_id = f'v66-finish-replay-{uuid.uuid4()}'
    r = _start(api, g)
    assert r.status_code == 201, r.text
    session_id = r.json()['session']['id']

    first = _finish(api, session_id, request_id=request_id, good_qty=4, defect_qty=1, rework_qty=0)
    assert first.status_code == 200, first.text
    assert first.json()['idempotent_replay'] is False

    second = _finish(api, session_id, request_id=request_id, good_qty=4, defect_qty=1, rework_qty=0)
    assert second.status_code == 200, second.text
    assert second.json()['idempotent_replay'] is True
    assert second.json()['session'] == first.json()['session']

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM audit_logs WHERE action='SESSION_FINISHED' AND entity_id=%s", (str(session_id),))
        count = cur.fetchone()['n']
    assert count == 1, 'a replayed FINISH must not create a second audit row'


def test_double_finish_is_still_rejected_as_a_conflict(db, api, seeded_factory):
    g = seeded_factory
    r = _start(api, g)
    session_id = r.json()['session']['id']
    first = _finish(api, session_id, good_qty=1, defect_qty=0, rework_qty=0)
    assert first.status_code == 200, first.text

    second = _finish(api, session_id, good_qty=1, defect_qty=0, rework_qty=0)  # new request_id -> not a replay
    assert second.status_code == 409, second.text
    assert second.json()['ok'] is False


def test_rework_greater_than_defect_is_still_rejected(db, api, seeded_factory):
    g = seeded_factory
    r = _start(api, g)
    session_id = r.json()['session']['id']
    r = _finish(api, session_id, good_qty=1, defect_qty=1, rework_qty=5)
    assert r.status_code == 400, r.text


def test_finishing_a_missing_session_is_not_found(api):
    r = _finish(api, 999_999_999)
    assert r.status_code == 404, r.text


def test_second_open_session_on_the_same_operation_is_a_conflict(api, seeded_factory):
    """Trước migration 0054 bài này tên là ..._for_same_employee_... và khẳng
    định một nhân viên chỉ được MỘT session OPEN. Luật đó đã đổi CÓ CHỦ Ý: nay
    họ giữ được nhiều việc cùng lúc. Thứ còn lại -- và là thứ bài này canh -- là
    không bao giờ hai session OPEN trên CÙNG một Operation.

    Bất biến đó không phải chi tiết cài đặt: tem QR Operation là thứ kiosk dùng
    để chọn session. Cho phép hai session cùng một Operation thì tem hết định
    danh được, và màn hình buộc phải bắt người đứng máy chọn tay."""
    g = seeded_factory
    first = _start(api, g)
    assert first.status_code == 201, first.text
    second = _start(api, g)
    assert second.status_code == 409, second.text


def test_same_employee_holds_three_open_sessions_on_different_operations(db, api, seeded_factory):
    """T1-T3: một người trông 2-3 máy cùng lúc -- lý do tồn tại của 0054."""
    g = seeded_factory
    ids = [_start(api, g).json()['session']['id']]
    for op_id in _extra_operations(db, g, 2):
        r = _start(api, g, operation_id=op_id)
        assert r.status_code == 201, r.text
        ids.append(r.json()['session']['id'])

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s AND status='OPEN'", (g['employee_id'],))
        assert cur.fetchone()['n'] == 3
    assert len(set(ids)) == 3


def test_finishing_one_session_leaves_the_others_open(db, api, seeded_factory):
    """T7/R6: chốt sản lượng một việc KHÔNG được đụng những việc còn lại.

    Đây đúng là ca mà guard chồng-giờ cũ sẽ chặn: session còn mở của cùng người
    phủ lên khoảng [started_at, finish_at) của session đang được đóng."""
    g = seeded_factory
    first_id = _start(api, g).json()['session']['id']
    other_op = _extra_operations(db, g, 1)[0]
    second_id = _start(api, g, operation_id=other_op).json()['session']['id']

    r = _finish(api, first_id, good_qty=3, defect_qty=0, rework_qty=0)
    assert r.status_code == 200, r.text
    assert r.json()['session']['status'] == 'CLOSED'

    with db.cursor() as cur:
        cur.execute('SELECT status FROM work_sessions WHERE id=%s', (second_id,))
        assert cur.fetchone()['status'] == 'OPEN', 'đóng việc này không được đóng lây việc kia'


def test_concurrent_start_on_the_same_operation_creates_exactly_one(db, api, seeded_factory):
    """T9: hai máy quét bấm start cùng một (nhân viên, Operation) cùng lúc.

    request_id KHÁC nhau nên đây không phải replay idempotency -- lưới duy nhất
    còn lại là uq_open_session_per_employee_operation."""
    import concurrent.futures as cf
    g = seeded_factory
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_start, api, g), pool.submit(_start, api, g)]
        results = [f.result() for f in futures]
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s AND status='OPEN'", (g['employee_id'],))
        assert cur.fetchone()['n'] == 1


def test_concurrent_start_on_different_operations_both_succeed(db, api, seeded_factory):
    """T10: đua trên hai Operation KHÁC nhau phải cùng thành công -- ràng buộc
    mới không được siết quá tay thành ra chỉ đổi chỗ nút thắt cũ."""
    import concurrent.futures as cf
    g = seeded_factory
    op_a, op_b = _extra_operations(db, g, 2)
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_start, api, g, operation_id=op_a),
                   pool.submit(_start, api, g, operation_id=op_b)]
        results = [f.result() for f in futures]
    assert [r.status_code for r in results] == [201, 201], [r.text for r in results]

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s AND status='OPEN'", (g['employee_id'],))
        assert cur.fetchone()['n'] == 2
