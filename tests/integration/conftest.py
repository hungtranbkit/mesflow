import os
import time
from datetime import datetime, timezone

import psycopg
import pytest
import requests

BASE_URL = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')
DATABASE_URL = os.environ['DATABASE_URL']


def wait_http(url: str, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code < 500:
                return
            last = f'{response.status_code}: {response.text[:200]}'
        except Exception as exc:  # pragma: no cover - diagnostic path
            last = repr(exc)
        time.sleep(1)
    raise RuntimeError(f'API unavailable: {last}')


@pytest.fixture(scope='session')
def db():
    with psycopg.connect(DATABASE_URL, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


@pytest.fixture(scope='session')
def api():
    wait_http(f'{BASE_URL}/api/system/ready')
    session = requests.Session()
    response = session.post(f'{BASE_URL}/api/auth/login', json={
        'username': os.environ.get('MESFLOW_TEST_USERNAME', 'admin'),
        'password': os.environ.get('MESFLOW_TEST_PASSWORD', 'Admin@123456'),
    }, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()['ok'] is True
    return session


@pytest.fixture()
def cross_midnight_shift(db):
    """Session Lifecycle Fix Plan Phase 8: a real, temporary cross-midnight
    shift fixture (22:00 -> 06:00, cross_midnight=TRUE) for tests that
    specifically want to exercise cross-midnight working-time logic --
    NEVER the real seeded NIGHT shift (18:00-00:00, cross_midnight=FALSE
    as of the migration that fixed it, confirmed via `SELECT * FROM
    work_shifts`), which does NOT cross midnight and was only ever
    incidentally usable for this because some OLDER tests assumed a
    different NIGHT definition than what's actually configured today. Per
    the fix plan's own instruction: "Không hardcode NIGHT logic ở test.
    Tests phải dựng shift fixture riêng khi muốn test cross-midnight."
    Yields {'id':..., 'code':...}; deletes the fixture (intervals cascade)
    on teardown."""
    import uuid
    code = f'TEST-XM-{uuid.uuid4().hex[:8]}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_shifts(code,name,timezone,anchor_start,anchor_end,cross_midnight,target_minutes,working_weekdays,sort_order,active)
            VALUES(%s,'Test Cross-Midnight','Asia/Ho_Chi_Minh','22:00','06:00',TRUE,480,'{0,1,2,3,4,5}',99,TRUE) RETURNING id""", (code,))
        shift_id = cur.fetchone()['id']
        # WORK 22:00-00:00, BREAK 00:00-01:00, WORK 01:00-06:00
        # (minute-of-anchor-day numbering, NOT modulo 1440 -- 1320=22:00,
        # 1800=30:00=06:00 the NEXT day, matching how shift_bounds()/
        # working_seconds_between() already interpret NIGHT's own
        # intervals in core/working_calendar.py). A real break, not just a
        # single unbroken block, so "...and_excludes_break" tests actually
        # exercise break-exclusion against a genuinely cross-midnight shift.
        cur.execute("""INSERT INTO work_shift_intervals(shift_id,interval_type,start_minute,end_minute,label,sort_order)
            VALUES(%s,'WORK',1320,1440,'Đầu ca',0),(%s,'BREAK',1440,1500,'Nghỉ giữa ca',1),(%s,'WORK',1500,1800,'Cuối ca',2)""",
            (shift_id, shift_id, shift_id))
    yield {'id': shift_id, 'code': code}
    with db.cursor() as cur:
        cur.execute('DELETE FROM work_shifts WHERE id=%s', (shift_id,))


@pytest.fixture()
def seeded_factory(db):
    """Create a minimal deterministic factory graph and remove it after each test."""
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f')
    with db.cursor() as cur:
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                    (f'TEST-{suffix}', 'Docker Test Worker', f'WF|EMP|TEST-{suffix}'))
        employee_id = cur.fetchone()['id']
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'Docker Test Station','TEST','TEST') RETURNING id",
                    (f'TEST-ST-{suffix}',))
        station_id = cur.fetchone()['id']
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'TEST PRODUCT',100,'IN_PROGRESS') RETURNING id",
                    (f'TEST-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Docker Test Part') RETURNING id",
                    (po_id, f'TEST-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                       VALUES(%s,%s,%s,'Docker Test Operation','IN_PROGRESS',%s) RETURNING id""",
                    (po_id, part_id, f'TEST-OP-{suffix}', f'WF|OP|TEST-OP-{suffix}'))
        operation_id = cur.fetchone()['id']
    graph = dict(employee_id=employee_id, station_id=station_id, po_id=po_id, part_id=part_id, operation_id=operation_id, suffix=suffix)
    yield graph
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_client_events WHERE server_session_id IN (SELECT id FROM work_sessions WHERE employee_id=%s)", (employee_id,))
        cur.execute("DELETE FROM kiosk_idempotency WHERE request_id IN (SELECT start_request_id FROM work_sessions WHERE employee_id=%s) OR request_id IN (SELECT finish_request_id FROM work_sessions WHERE employee_id=%s)", (employee_id, employee_id))
        cur.execute("DELETE FROM operation_adjustments WHERE session_id IN (SELECT id FROM work_sessions WHERE employee_id=%s)", (employee_id,))
        cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (employee_id,))
        cur.execute("DELETE FROM operations WHERE id=%s", (operation_id,))
        cur.execute("DELETE FROM parts WHERE id=%s", (part_id,))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (po_id,))
        cur.execute("DELETE FROM stations WHERE id=%s", (station_id,))
        cur.execute("DELETE FROM employees WHERE id=%s", (employee_id,))
