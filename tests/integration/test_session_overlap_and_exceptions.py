from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def insert_session(db, graph, key, start, end, good=0):
    return db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
                       VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,%s,0,%s,%s) RETURNING id""",
                      (graph['employee_id'], graph['operation_id'], graph['station_id'], start, end, good,
                       f'start-{key}-{graph["suffix"]}', f'finish-{key}-{graph["suffix"]}')).fetchone()['id']


def test_admin_edit_rejects_overlapping_session(db, api, seeded_factory):
    g = seeded_factory
    first = insert_session(db, g, 'first', datetime(2026,8,6,8,0,tzinfo=HCM), datetime(2026,8,6,10,0,tzinfo=HCM), 5)
    second = insert_session(db, g, 'second', datetime(2026,8,6,10,0,tzinfo=HCM), datetime(2026,8,6,11,0,tzinfo=HCM), 2)
    response = api.patch(f'http://mesflow-test-api:8080/api/supervisor/sessions/{second}', json={
        'started_at': '2026-08-06T09:30:00+07:00',
        'ended_at': '2026-08-06T11:00:00+07:00',
        'status': 'CLOSED',
        'reason': 'Docker E2E overlap check',
    }, timeout=10)
    assert response.status_code == 409, response.text
    assert f'Session #{first}' in response.json()['message']


def test_half_open_boundary_allows_adjacent_sessions(db, api, seeded_factory):
    g = seeded_factory
    insert_session(db, g, 'adjacent-first', datetime(2026,8,6,8,0,tzinfo=HCM), datetime(2026,8,6,10,0,tzinfo=HCM), 5)
    second = insert_session(db, g, 'adjacent-second', datetime(2026,8,6,10,30,tzinfo=HCM), datetime(2026,8,6,11,30,tzinfo=HCM), 2)
    response = api.patch(f'http://mesflow-test-api:8080/api/supervisor/sessions/{second}', json={
        'started_at': '2026-08-06T10:00:00+07:00',
        'ended_at': '2026-08-06T11:00:00+07:00',
        'status': 'CLOSED',
        'reason': 'Docker E2E adjacent boundary check',
    }, timeout=10)
    assert response.status_code == 200, response.text


def test_exception_center_detects_historical_overlap(db, api, seeded_factory):
    g = seeded_factory
    first = insert_session(db, g, 'history-first', datetime(2026,8,5,8,0,tzinfo=HCM), datetime(2026,8,5,10,0,tzinfo=HCM))
    second = insert_session(db, g, 'history-second', datetime(2026,8,5,9,30,tzinfo=HCM), datetime(2026,8,5,11,0,tzinfo=HCM))
    response = api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100', timeout=10)
    assert response.status_code == 200, response.text
    overlaps = [x for x in response.json()['items'] if x['exception_code'] == 'OVERLAP']
    ids = {x['session_id'] for x in overlaps}
    assert first in ids or second in ids
