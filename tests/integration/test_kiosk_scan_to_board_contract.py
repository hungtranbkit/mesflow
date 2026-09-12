"""Quét ở kiosk xong thì màn hình điều hành phải THẤY việc đó.

BUG P0 (2026-09-12, báo từ TEST). Người dùng mô phỏng một lượt quét trên
`/kiosk`: chọn nhân viên -> chọn Operation -> Start. Máy báo "Đã bắt đầu",
nhưng bảng task của Kiosk điều hành không đổi gì.

Không phải simulator giả. Bảng mô phỏng trong `/kiosk` bơm đúng chuỗi QR vào
`scan()` mà súng quét bơm vào, đi đúng `POST /api/kiosk-web/scan` rồi
`POST /api/kiosk-web/start`, và `work_sessions` có hàng OPEN thật. Đo được lúc
đó: HTTP 201, session OPEN trong DB, `SESSION_STARTED` chạy trên dòng hoạt động
ngay cạnh -- mà bảng task rỗng.

Chỗ gãy là một MÂU THUẪN HỢP ĐỒNG giữa hai đầu:

    kiosk MỞ ĐƯỢC session trên   STARTABLE_TYPES = {PRODUCTION, SETUP}
    màn hình lớn CHỈ HIỆN        PRODUCTION

Tem SETUP bắt buộc phải có (quét nó là cách DUY NHẤT ghi nhận việc chuẩn bị
máy -- xem domain/policy.py), nên "không cho start SETUP nữa" là hướng sai.
Cái sai là màn hình lớn giấu một ca làm việc có thật, và đếm thiếu người đang
làm: đo được DB có 2 session OPEN trong khi KPI báo 1.

Bộ bài dưới đây khoá HỢP ĐỒNG, không khoá cách cài đặt:

  * thứ gì kiosk start thành công thì phải thành một dòng task nhìn thấy được;
  * KPI "đang mở" / "người đang làm" phải đếm ĐÚNG số trong DB;
  * PO khác vẫn không lọt vào;
  * không có 2xx nào được phát ra khi không ghi được dữ liệu;
  * dòng task bám theo operation_id chuẩn, không bám mã.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]

HCM = timezone(timedelta(hours=7))


def _today() -> str:
    return datetime.now(HCM).date().isoformat()


@pytest.fixture()
def floor(db):
    """Một PO IN_PROGRESS có đủ hai loại Operation kiosk mở được, + một PO thứ hai."""
    tag = uuid.uuid4().hex[:8].upper()
    made: dict = {'tag': tag, 'employees': []}
    with db.cursor() as cur:
        def employee(suffix, name):
            cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
                VALUES(%s,%s,'TEST','Worker',%s,true) RETURNING id,employee_no,qr""",
                (f'{suffix}-{tag}', name, f'WF|EMP|{suffix}-{tag}'))
            row = dict(cur.fetchone())
            made['employees'].append(row['id'])
            return row

        def order(label):
            cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
                VALUES(%s,%s,100,'IN_PROGRESS') RETURNING id,code""",
                (f'PO-{label}-{tag}', f'Sản phẩm {label}'))
            po = dict(cur.fetchone())
            cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,%s,'Thân',0,true) RETURNING id,code""", (po['id'], f'PART-{label}-{tag}'))
            po['part'] = dict(cur.fetchone())
            return po

        def operation(po, code, name, op_type, sort_order, parent=None):
            cur.execute("""INSERT INTO operations
                  (production_order_id,part_id,code,name,status,qr,sort_order,operation_type,parent_operation_id)
                VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,%s,%s,%s) RETURNING id,code,name,qr""",
                (po['id'], po['part']['id'], f'{code}-{tag}', name, f'WF|OP|{code}-{tag}',
                 sort_order, op_type, parent))
            return dict(cur.fetchone())

        main = order('MAIN')
        other = order('OTHER')
        made['po'] = main
        made['other_po'] = other
        made['production'] = operation(main, 'OPP', 'Cắt laser', 'PRODUCTION', 0)
        made['setup'] = operation(main, 'OPS', 'Chuẩn bị máy', 'SETUP', 1,
                                  parent=made['production']['id'])
        # Cùng TÊN với OP sản xuất ở trên, khác mã: dòng task phải bám id, không
        # được bám cái người đọc nhìn thấy.
        made['twin'] = operation(main, 'OPT', 'Cắt laser', 'PRODUCTION', 2)
        made['other_op'] = operation(other, 'OPX', 'Cắt PO khác', 'PRODUCTION', 0)
        made['worker'] = employee('W1', 'Thợ Sản Xuất')
        made['setter'] = employee('W2', 'Thợ Chuẩn Bị')
        made['twin_worker'] = employee('W3', 'Thợ Song Sinh')
        made['other_worker'] = employee('W4', 'Thợ PO Khác')

    yield made

    with db.cursor() as cur:
        for po in (made['po'], made['other_po']):
            cur.execute('DELETE FROM production_trace_events WHERE production_order_id=%s', (po['id'],))
            cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
                           (SELECT id FROM operations WHERE production_order_id=%s)""", (po['id'],))
            # SETUP phải luôn có parent (ck_operations_setup_has_parent), nên gỡ
            # con trước rồi mới tới cha -- không có đường "gỡ liên kết" nào hợp lệ.
            cur.execute("DELETE FROM operations WHERE production_order_id=%s AND operation_type='SETUP'", (po['id'],))
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po['id'],))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po['id'],))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po['id'],))
        cur.execute('DELETE FROM work_sessions WHERE employee_id = ANY(%s)', (made['employees'],))
        cur.execute('DELETE FROM employees WHERE id = ANY(%s)', (made['employees'],))


def _scan(api, qr):
    return api.post(f'{BASE_URL}/api/kiosk-web/scan', json={'qr': qr}, timeout=25)


def _start(api, employee_id, operation_id, tag=''):
    """Đúng payload kiosk.js gửi: operation_id CHUẨN, kèm request_id idempotent."""
    return api.post(f'{BASE_URL}/api/kiosk-web/start', json={
        'employee_id': employee_id, 'operation_id': operation_id,
        'device_uuid': f'WEB-TEST-{tag}',
        'request_id': f'{tag}-START-{uuid.uuid4().hex[:10]}',
    }, timeout=25)


def _board(api, po_id, date=None):
    response = api.get(f'{BASE_URL}/api/kiosk-board?po_id={po_id}&date={date or _today()}', timeout=25)
    assert response.status_code == 200, response.text
    return response.json()


def _task_ids(board):
    return {int(t['operation_id']) for t in board['tasks']}


def _scan_then_start(api, employee, operation, tag):
    """Đúng chuỗi thao tác của người dùng: quét thẻ -> quét tem -> Start."""
    first = _scan(api, employee['qr'])
    assert first.status_code == 200, first.text
    assert first.json()['type'] == 'employee'
    second = _scan(api, operation['qr'])
    assert second.status_code == 200, second.text
    assert second.json()['type'] == 'operation'
    # kiosk.js gửi `op.id` lấy từ CHÍNH phản hồi scan -- không tự tra lại theo mã.
    resolved = int(second.json()['operation']['id'])
    assert resolved == int(operation['id'])
    return _start(api, employee['id'], resolved, tag)


class TestScanBecomesAVisibleTask:
    """(1) start thành công -> DB có session OPEN -> endpoint dashboard có đúng task đó."""

    def test_a_started_production_operation_appears_on_the_board(self, api, db, floor):
        started = _scan_then_start(api, floor['worker'], floor['production'], floor['tag'])
        assert started.status_code == 201, started.text
        session_id = int(started.json()['session']['id'])

        with db.cursor() as cur:
            cur.execute('SELECT status,operation_id FROM work_sessions WHERE id=%s', (session_id,))
            row = cur.fetchone()
        assert row['status'] == 'OPEN'
        assert int(row['operation_id']) == int(floor['production']['id'])

        board = _board(api, floor['po']['id'])
        assert int(floor['production']['id']) in _task_ids(board), \
            f"task vừa start không có trên bảng: {board['tasks']}"

    def test_a_started_setup_operation_appears_on_the_board(self, api, db, floor):
        """HỒI QUY CHÍNH của bug P0.

        SETUP nằm trong STARTABLE_TYPES nên kiosk mở được session, và tem SETUP
        là cách duy nhất ghi nhận việc chuẩn bị máy. Trước bản vá, đúng lượt quét
        này trả 201 kèm session OPEN thật mà bảng task không hiện dòng nào.
        """
        started = _scan_then_start(api, floor['setter'], floor['setup'], floor['tag'])
        assert started.status_code == 201, started.text
        session_id = int(started.json()['session']['id'])

        with db.cursor() as cur:
            cur.execute('SELECT status FROM work_sessions WHERE id=%s', (session_id,))
            assert cur.fetchone()['status'] == 'OPEN'

        board = _board(api, floor['po']['id'])
        assert int(floor['setup']['id']) in _task_ids(board), \
            f"ca chuẩn bị máy có thật nhưng bảng task giấu đi: {board['tasks']}"

    def test_the_board_says_what_kind_of_work_a_support_task_is(self, api, floor):
        """Dòng task phải mang loại Operation, nếu không màn hình vẽ "0 / 100".

        OP phụ không có chỉ tiêu sản lượng; hiện nó bằng đúng ô Đạt/Kế hoạch của
        OP sản xuất đọc ra như một công đoạn đang tụt tiến độ.
        """
        _scan_then_start(api, floor['setter'], floor['setup'], floor['tag'])
        board = _board(api, floor['po']['id'])
        row = next(t for t in board['tasks'] if int(t['operation_id']) == int(floor['setup']['id']))
        assert str(row.get('operation_type') or '').upper() == 'SETUP'

    def test_finishing_does_not_make_the_task_vanish(self, api, floor):
        """Kết thúc xong task vẫn còn trên bảng (đổi trạng thái), không bốc hơi."""
        started = _scan_then_start(api, floor['worker'], floor['production'], floor['tag'])
        session_id = int(started.json()['session']['id'])
        finished = api.post(f'{BASE_URL}/api/kiosk-web/finish/{session_id}',
                            json={'good_qty': 5, 'defect_qty': 0, 'rework_qty': 0,
                                  'request_id': f"{floor['tag']}-FIN"}, timeout=25)
        assert finished.status_code == 200, finished.text

        board = _board(api, floor['po']['id'])
        assert int(floor['production']['id']) in _task_ids(board)
        row = next(t for t in board['tasks'] if int(t['operation_id']) == int(floor['production']['id']))
        assert row['day_state'] in ('UPDATED', 'RUNNING', 'NEEDS_REVIEW')


class TestLiveCountsTellTheTruth:
    """KPI "đang mở" / "người đang làm" phải khớp DB -- đây là chỗ bug đếm thiếu."""

    def test_open_session_and_worker_counts_match_the_database(self, api, db, floor):
        _scan_then_start(api, floor['worker'], floor['production'], floor['tag'])
        _scan_then_start(api, floor['setter'], floor['setup'], floor['tag'])

        with db.cursor() as cur:
            cur.execute("""SELECT COUNT(*) open_sessions,COUNT(DISTINCT ws.employee_id) workers
                           FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
                           WHERE o.production_order_id=%s AND ws.status='OPEN'""",
                        (floor['po']['id'],))
            truth = cur.fetchone()

        kpis = _board(api, floor['po']['id'])['kpis']
        assert kpis['open_session_count'] == truth['open_sessions'], \
            'KPI "session đang mở" đếm thiếu ca đang chạy'
        assert kpis['active_worker_count'] == truth['workers'], \
            'KPI "người đang làm" bỏ sót người đang đứng máy'


class TestNothingElseLeaksIn:
    """(3) PO khác vẫn phải cô lập -- mở rộng loại Operation không được nới phạm vi PO."""

    def test_another_pos_started_task_never_appears(self, api, floor):
        _scan_then_start(api, floor['worker'], floor['production'], floor['tag'])
        _scan_then_start(api, floor['other_worker'], floor['other_op'], floor['tag'])

        board = _board(api, floor['po']['id'])
        foreign = [t for t in board['tasks'] if int(t['po_id']) != int(floor['po']['id'])]
        assert not foreign, f'task của PO khác lọt vào: {foreign}'
        assert int(floor['other_op']['id']) not in _task_ids(board)

        other = _board(api, floor['other_po']['id'])
        assert int(floor['other_op']['id']) in _task_ids(other)
        assert int(floor['production']['id']) not in _task_ids(other)


class TestSuccessAlwaysMeansPersisted:
    """(4) Không được phát 2xx khi không ghi được dữ liệu."""

    def test_a_rejected_start_creates_no_session_and_no_success(self, api, db, floor):
        first = _scan_then_start(api, floor['worker'], floor['production'], floor['tag'])
        assert first.status_code == 201, first.text

        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s',
                        (floor['worker']['id'],))
            before = cur.fetchone()['n']

        # Cùng một người không thể mở hai ca (uq_open_session_per_employee).
        second = _start(api, floor['worker']['id'], floor['twin']['id'], floor['tag'])
        assert second.status_code >= 400, \
            f'start thứ hai báo thành công {second.status_code}: {second.text}'
        assert second.json().get('ok') is not True

        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s',
                        (floor['worker']['id'],))
            assert cur.fetchone()['n'] == before, 'ghi thêm session dù đã báo lỗi'

        board = _board(api, floor['po']['id'])
        assert int(floor['twin']['id']) not in _task_ids(board), \
            'task hiện lên cho một lượt start đã bị từ chối'

    def test_a_paused_po_cannot_be_started_at_all(self, api, db, floor):
        with db.cursor() as cur:
            cur.execute("UPDATE production_orders SET status='PAUSED' WHERE id=%s", (floor['po']['id'],))
        try:
            scanned = _scan(api, floor['production']['qr'])
            assert scanned.status_code == 409, scanned.text
            assert scanned.json()['error_code'] == 'PO-001'
            started = _start(api, floor['worker']['id'], floor['production']['id'], floor['tag'])
            assert started.status_code >= 400
            with db.cursor() as cur:
                cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s',
                            (floor['production']['id'],))
                assert cur.fetchone()['n'] == 0
        finally:
            with db.cursor() as cur:
                cur.execute("UPDATE production_orders SET status='IN_PROGRESS' WHERE id=%s",
                            (floor['po']['id'],))


class TestOperationIdentityIsCanonical:
    """(5) Mã Operation không được quyết định task nào hiện lên."""

    def test_two_operations_sharing_a_name_never_swap_places(self, api, floor):
        """`twin` mang ĐÚNG tên của `production`, khác mã và khác id.

        Nếu bảng task bám theo thứ người đọc nhìn thấy thay vì id chuẩn, lượt
        start này sẽ hiện nhầm dòng -- hoặc không hiện dòng nào.
        """
        assert floor['twin']['name'] == floor['production']['name']
        started = _scan_then_start(api, floor['twin_worker'], floor['twin'], floor['tag'])
        assert started.status_code == 201, started.text

        board = _board(api, floor['po']['id'])
        assert int(floor['twin']['id']) in _task_ids(board)
        assert int(floor['production']['id']) not in _task_ids(board), \
            'start trên OP này lại làm OP trùng tên hiện lên'

    def test_an_opid_qr_resolves_to_exactly_that_operation(self, api, floor):
        """Tem mới mang `WF|OPID|<id>` chính vì mã không phải định danh bền."""
        response = _scan(api, f"WF|OPID|{floor['setup']['id']}")
        assert response.status_code == 200, response.text
        assert int(response.json()['operation']['id']) == int(floor['setup']['id'])
