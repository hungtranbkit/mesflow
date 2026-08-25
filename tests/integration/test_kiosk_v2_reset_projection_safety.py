"""Regression coverage for scripts/kiosk_v2_reset_projection.py's core safety
guard: a real footgun this session (an ad-hoc UPDATE silently overwrote a
device's projection while a real Work Session was still OPEN) must never
recur. See that script's module docstring for the incident.

Runs against whatever DATABASE_URL/db fixture this test session already
uses (compose.test.yml's mesflow_test, normally) -- reset_projection()
itself has no environment-naming opinion (that's the CLI wrapper's job, in
main()), so this exercises the real safety logic without needing a
database literally named "local_test".
"""
import sys
import uuid
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from kiosk_v2_reset_projection import reset_projection, OpenSessionRefused  # noqa: E402
from mesflow.db.repositories.execution import WorkSessionRepository  # noqa: E402


def _device_id(suffix):
    return f'TEST-KIOSK-RESET-{suffix}'


def _seed_projection(db, device_id, **fields):
    cols = ', '.join(['device_id'] + list(fields.keys()))
    placeholders = ', '.join(['%s'] * (1 + len(fields)))
    with db.cursor() as cur:
        cur.execute(
            f'INSERT INTO kiosk_v2_projection({cols}) VALUES ({placeholders}) '
            'ON CONFLICT (device_id) DO UPDATE SET '
            + ', '.join(f'{k}=EXCLUDED.{k}' for k in fields)
            + ' RETURNING state_version',
            [device_id] + list(fields.values()))
        return cur.fetchone()['state_version']


def test_refuses_reset_while_session_open(db, seeded_factory):
    g = seeded_factory
    device_id = _device_id(g['suffix'])
    result = WorkSessionRepository().start({
        'request_id': f'test-start-{uuid.uuid4()}', 'employee_id': g['employee_id'],
        'operation_id': g['operation_id'], 'station_id': g['station_id'], 'device_uuid': device_id,
    })
    session_id = result['session']['id']
    _seed_projection(db, device_id, state_name='SESSION_ACTIVE', work_session_id=session_id,
                     employee_id=g['employee_id'], operation_id=g['operation_id'])

    try:
        reset_projection(device_id)
        assert False, 'expected OpenSessionRefused'
    except OpenSessionRefused as exc:
        assert str(session_id) in str(exc)

    # Nothing touched: session still OPEN, projection still points at it.
    with db.cursor() as cur:
        cur.execute('SELECT status FROM work_sessions WHERE id=%s', (session_id,))
        assert cur.fetchone()['status'] == 'OPEN'
        cur.execute('SELECT state_name, work_session_id FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
        row = cur.fetchone()
        assert row['state_name'] == 'SESSION_ACTIVE'
        assert row['work_session_id'] == session_id


def test_force_close_zero_closes_via_real_business_service(db, seeded_factory):
    g = seeded_factory
    device_id = _device_id(g['suffix'] + '-force')
    result = WorkSessionRepository().start({
        'request_id': f'test-start-{uuid.uuid4()}', 'employee_id': g['employee_id'],
        'operation_id': g['operation_id'], 'station_id': g['station_id'], 'device_uuid': device_id,
    })
    session_id = result['session']['id']
    _seed_projection(db, device_id, state_name='SESSION_ACTIVE', work_session_id=session_id,
                     employee_id=g['employee_id'], operation_id=g['operation_id'])

    out = reset_projection(device_id, force_close_zero=True)
    assert out['closed_session_id'] == session_id

    with db.cursor() as cur:
        cur.execute('SELECT status, good_qty, defect_qty, rework_qty, finish_request_id '
                   'FROM work_sessions WHERE id=%s', (session_id,))
        row = cur.fetchone()
        assert row['status'] == 'CLOSED'
        assert row['good_qty'] == 0 and row['defect_qty'] == 0 and row['rework_qty'] == 0
        assert row['finish_request_id'].startswith('admin-reset:')
        cur.execute('SELECT state_name, work_session_id FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
        row = cur.fetchone()
        assert row['state_name'] == 'WAIT_EMPLOYEE'
        assert row['work_session_id'] is None


def test_no_open_session_resets_cleanly(db, seeded_factory):
    g = seeded_factory
    device_id = _device_id(g['suffix'] + '-clean')
    _seed_projection(db, device_id, state_name='WAIT_OPERATION', work_session_id=None,
                     employee_id=g['employee_id'])

    out = reset_projection(device_id)
    assert out['action'] == 'reset'
    assert out['closed_session_id'] is None

    with db.cursor() as cur:
        cur.execute('SELECT state_name FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
        assert cur.fetchone()['state_name'] == 'WAIT_EMPLOYEE'
