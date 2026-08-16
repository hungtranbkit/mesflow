"""Redesigned Business Audit Trail -- integration coverage against the real
running mesflow-test-api + Postgres (section 15/16): real employee/operation
rows via seeded_factory, real audit_logs writes, real HTTP GET /api/audit-logs,
asserting the enriched `presentation` on each item and that batched
enrichment stays bounded (no N+1) as the page grows.
"""
import json
import uuid

import pytest

from mesflow.db import connection as db_connection
from mesflow.db.repositories import analytics as analytics_repo

pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'


def _insert_audit(db, action, entity_type, entity_id, details, actor='admin'):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,details_json) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (actor, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False)),
        )
        return cur.fetchone()['id']


def test_session_edit_audit_row_shows_human_presentation_over_http(api, db, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,rework_qty,note,start_request_id,finish_request_id)
               VALUES(%s,%s,%s,'CLOSED',%s,%s,10,1,0,'',%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], '2026-08-09T10:00:00+00:00', '2026-08-09T11:00:00+00:00',
             f"s-{g['suffix']}", f"f-{g['suffix']}"),
        )
        session_id = cur.fetchone()['id']
    old = {'id': session_id, 'employee_id': g['employee_id'], 'operation_id': g['operation_id'], 'station_id': g['station_id'],
           'status': 'CLOSED', 'started_at': '2026-08-09T10:39:07.380249+00:00', 'ended_at': '2026-08-09T11:00:00+00:00',
           'good_qty': 10, 'defect_qty': 1, 'rework_qty': 0, 'note': '', 'updated_at': '2026-08-09T11:00:00+00:00'}
    new = {**old, 'started_at': '2026-08-09T10:39:00+00:00', 'updated_at': '2026-08-09T11:05:00+00:00'}
    _insert_audit(db, 'SESSION_EDIT', 'work_session', str(session_id), {'reason': 'ok', 'old': old, 'new': new})

    r = api.get(f'{BASE}/api/audit-logs?entity_type=work_session&entity_id={session_id}', timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()['items']
    row = next(x for x in items if x['action'] == 'SESSION_EDIT')
    p = row['presentation']
    assert p['title'] == f'Chỉnh sửa Session #{session_id}'
    assert p['context']['employee']['name'] == 'Docker Test Worker'
    assert p['context']['operation']['name'] == 'Docker Test Operation'
    assert len(p['changes']) == 1 and p['changes'][0]['field'] == 'started_at'
    # raw evidence is preserved, untouched, alongside the presentation -- never removed.
    assert row['details_json']['old']['good_qty'] == 10
    assert row['details_json']['new']['started_at'] == '2026-08-09T10:39:00+00:00'


def test_session_exception_workflow_update_resolves_employee_and_operation_via_session(api, db, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
               VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], f"open-{g['suffix']}"),
        )
        session_id = cur.fetchone()['id']
    _insert_audit(db, 'SESSION_EXCEPTION_WORKFLOW_UPDATE', 'session_exception', 'bulk', {
        'workflow_status': 'IN_PROGRESS', 'note': '', 'assigned_to': 'admin', 'resolution': '',
        'items': [{'session_id': session_id, 'exception_code': 'OPEN_TOO_LONG', 'exception_fingerprint': f'OPEN_TOO_LONG:{session_id}'}],
    })

    r = api.get(f'{BASE}/api/audit-logs?action=SESSION_EXCEPTION_WORKFLOW_UPDATE&limit=5', timeout=10)
    assert r.status_code == 200, r.text
    row = r.json()['items'][0]
    p = row['presentation']
    assert p['title'] == 'Xử lý Session bất thường'
    assert f'Session #{session_id}' in p['summary']
    assert p['context']['employee']['name'] == 'Docker Test Worker'
    values = {e['field']: e['value'] for e in p['extra']}
    assert values['exception_code'] == 'Session mở quá lâu'
    # normal-view payload text must never contain the raw fingerprint/code pair
    dump = json.dumps(p, ensure_ascii=False)
    assert 'exception_fingerprint' not in dump
    with db.cursor() as cur:
        cur.execute('DELETE FROM work_sessions WHERE id=%s', (session_id,))


def test_work_shifts_replace_audit_row_over_http(api, db):
    marker = f'WSR-{uuid.uuid4().hex[:8]}'
    _insert_audit(db, 'WORK_SHIFTS_REPLACE', 'work_shift', marker, {'items': [
        {'code': 'DAY', 'name': 'Ca ngày', 'active': True, 'intervals': [{'interval_type': 'WORK', 'start_minute': 450, 'end_minute': 1020}]},
    ]})
    r = api.get(f'{BASE}/api/audit-logs?entity_type=work_shift&entity_id={marker}', timeout=10)
    assert r.status_code == 200, r.text
    row = r.json()['items'][0]
    p = row['presentation']
    assert p['title'] == 'Cập nhật lịch làm việc'
    assert p['shifts'][0]['span'] == '07:30 – 17:00'
    dump = json.dumps(p, ensure_ascii=False)
    assert 'interval_type' not in dump


def test_category_filter_only_returns_matching_actions(api, db):
    marker = f'CATFILT-{uuid.uuid4().hex[:8]}'
    _insert_audit(db, 'WORK_SHIFTS_REPLACE', 'work_shift', marker, {'items': []})
    r = api.get(f'{BASE}/api/audit-logs?category=calendar&limit=50', timeout=10)
    assert r.status_code == 200, r.text
    actions = {x['action'] for x in r.json()['items']}
    assert actions <= {'WORK_SHIFTS_REPLACE'}
    r2 = api.get(f'{BASE}/api/audit-logs?category=session&limit=50', timeout=10)
    assert 'WORK_SHIFTS_REPLACE' not in {x['action'] for x in r2.json()['items']}


def test_unknown_category_returns_empty_not_error(api):
    r = api.get(f'{BASE}/api/audit-logs?category=not_a_real_category', timeout=10)
    assert r.status_code == 200
    assert r.json()['items'] == []


def test_enrichment_uses_bounded_query_count_not_n_plus_1(db, seeded_factory):
    """section 8: 'Do not introduce expensive N+1 queries.' Insert several
    SESSION_EDIT rows for DIFFERENT sessions/employees and confirm the
    number of enrichment queries stays constant (batched), not
    proportional to row count."""
    session_ids = []
    with db.cursor() as cur:
        for i in range(6):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'N1-{i}-{uuid.uuid4().hex[:6]}', f'N+1 Worker {i}', f'WF|EMP|N1-{i}-{uuid.uuid4().hex[:6]}'))
            emp_id = cur.fetchone()['id']
            cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'N1 Station','TEST','TEST') RETURNING id", (f'N1-ST-{i}-{uuid.uuid4().hex[:6]}',))
            st_id = cur.fetchone()['id']
            cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'P',10,'IN_PROGRESS') RETURNING id", (f'N1-PO-{i}-{uuid.uuid4().hex[:6]}',))
            po_id = cur.fetchone()['id']
            cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Part') RETURNING id", (po_id, f'N1-PART-{i}-{uuid.uuid4().hex[:6]}'))
            part_id = cur.fetchone()['id']
            cur.execute("INSERT INTO operations(production_order_id,part_id,code,name,status,qr) VALUES(%s,%s,%s,'Op','IN_PROGRESS',%s) RETURNING id",
                        (po_id, part_id, f'N1-OP-{i}-{uuid.uuid4().hex[:6]}', f'WF|OP|N1-{i}-{uuid.uuid4().hex[:6]}'))
            op_id = cur.fetchone()['id']
            cur.execute("INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id) VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP,%s) RETURNING id",
                        (emp_id, op_id, st_id, f'n1-{i}-{uuid.uuid4().hex[:8]}'))
            sid = cur.fetchone()['id']
            session_ids.append(sid)
            snap = {'id': sid, 'employee_id': emp_id, 'operation_id': op_id, 'station_id': st_id, 'status': 'OPEN',
                    'started_at': '2026-08-09T10:00:00+00:00', 'ended_at': None, 'good_qty': 0, 'defect_qty': 0, 'rework_qty': 0, 'note': ''}
            _insert_audit(db, 'SESSION_ADJUST', 'work_session', str(sid), {'good_qty': 1})

    query_count = {'n': 0}
    orig_fetch_all = db_connection.fetch_all
    def counting_fetch_all(*a, **k):
        query_count['n'] += 1
        return orig_fetch_all(*a, **k)
    analytics_repo.fetch_all = counting_fetch_all
    try:
        rows = analytics_repo.AuditRepository().list(limit=20, entity_type='work_session')
    finally:
        analytics_repo.fetch_all = orig_fetch_all
    assert len(rows) >= 6
    # 1 page query + up to 4 batched enrichment queries (sessions/employees/operations/stations) = 5, never one per row.
    assert query_count['n'] <= 5, f'expected a bounded, batched query count, got {query_count["n"]}'
