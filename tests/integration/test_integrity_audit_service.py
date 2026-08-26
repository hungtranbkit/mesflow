"""Reliability Validation Round 2, Gate 3 -- read-only database invariant
auditor, against real PostgreSQL. Confirms each category actually detects
the condition it claims to, and that it never mutates data."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from mesflow.services.integrity_audit_service import audit_integrity

pytestmark = pytest.mark.postgres


def test_audit_integrity_never_mutates_data(db, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions")
        before = cur.fetchone()['n']
    audit_integrity()
    audit_integrity()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions")
        after = cur.fetchone()['n']
    assert before == after


def _insert_session(db, g, **overrides):
    fields = dict(
        employee_id=g['employee_id'], operation_id=g['operation_id'], station_id=g['station_id'],
        status='OPEN', started_at=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc), ended_at=None,
        good_qty=0, defect_qty=0, rework_qty=0,
        start_request_id=f'AUDIT-{uuid.uuid4().hex[:12]}', finish_request_id=None,
    )
    fields.update(overrides)
    cols = list(fields.keys())
    with db.cursor() as cur:
        cur.execute(
            f"INSERT INTO work_sessions({','.join(cols)}) VALUES({','.join(['%s'] * len(cols))}) RETURNING id",
            [fields[c] for c in cols],
        )
        return cur.fetchone()['id']


def test_status_ended_at_mismatch_detects_closed_without_ended_at(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='CLOSED', ended_at=None,
                           finish_request_id=f'AUDIT-F-{uuid.uuid4().hex[:12]}')
    result = audit_integrity()
    assert any(x['id'] == sid for x in result['STATUS_ENDED_AT_MISMATCH'])


def test_status_ended_at_mismatch_detects_open_with_ended_at(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='OPEN',
                           ended_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc))
    result = audit_integrity()
    assert any(x['id'] == sid for x in result['STATUS_ENDED_AT_MISMATCH'])


def test_negative_quantity_detected(db, seeded_factory):
    g = seeded_factory
    # good_qty/defect_qty have no DB CHECK constraint (only rework_qty
    # does) -- raw SQL is the only way to actually produce this row, which
    # is exactly why the audit checks for it rather than trusting the
    # application layer alone.
    sid = _insert_session(db, g, status='CLOSED',
                           ended_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
                           good_qty=-5, finish_request_id=f'AUDIT-F-{uuid.uuid4().hex[:12]}')
    result = audit_integrity()
    assert any(x['id'] == sid for x in result['NEGATIVE_QUANTITY'])


def test_ended_before_started_detected(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='CLOSED',
                           started_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
                           ended_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
                           finish_request_id=f'AUDIT-F-{uuid.uuid4().hex[:12]}')
    result = audit_integrity()
    assert any(x['id'] == sid for x in result['ENDED_BEFORE_STARTED'])


def test_multiple_open_per_employee_bypassing_partial_unique_index(db, seeded_factory):
    g = seeded_factory
    _insert_session(db, g, status='OPEN')
    # uq_open_session_per_employee (migration 0003) would reject a second
    # OPEN row for the same employee through the normal INSERT path --
    # dropping the constraint for the duration of this test is the only
    # way to prove the audit catches a bypass rather than merely restating
    # what the constraint already guarantees.
    with db.cursor() as cur:
        cur.execute('DROP INDEX IF EXISTS uq_open_session_per_employee')
    try:
        _insert_session(db, g, status='OPEN', started_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc))
        result = audit_integrity()
        assert any(x['employee_id'] == g['employee_id'] and x['open_count'] >= 2
                   for x in result['MULTIPLE_OPEN_PER_EMPLOYEE'])
    finally:
        with db.cursor() as cur:
            cur.execute("DELETE FROM work_sessions WHERE employee_id=%s AND status='OPEN'", (g['employee_id'],))
            cur.execute("CREATE UNIQUE INDEX uq_open_session_per_employee ON work_sessions(employee_id) WHERE status='OPEN'")


def test_operation_completed_session_still_open_detected(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='OPEN')
    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='COMPLETED' WHERE id=%s", (g['operation_id'],))
    result = audit_integrity()
    assert any(x['session_id'] == sid for x in result['OPERATION_COMPLETED_SESSION_STILL_OPEN'])


def test_auto_close_changed_quantity_detected(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='CLOSED',
                           ended_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
                           finish_request_id=f'AUDIT-F-{uuid.uuid4().hex[:12]}')
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_trace_events(event_type,category,session_id,operation_id,title,quantity_delta)
            VALUES('SESSION_AUTO_CLOSED','SESSION',%s,%s,'test',5) RETURNING id""", (sid, g['operation_id']))
        event_id = cur.fetchone()['id']
    try:
        result = audit_integrity()
        assert any(x['id'] == event_id for x in result['AUTO_CLOSE_CHANGED_QUANTITY'])
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM production_trace_events WHERE id=%s', (event_id,))


def test_duplicate_quantity_movement_detected(db, seeded_factory):
    g = seeded_factory
    sid = _insert_session(db, g, status='OPEN')
    correlation_id = f'AUDIT-CORR-{uuid.uuid4().hex[:12]}'
    try:
        with db.cursor() as cur:
            for _ in range(2):
                cur.execute("""INSERT INTO quantity_movements(movement_type,delta,previous_value,new_value,operation_id,session_id,source,correlation_id)
                    VALUES('GOOD',3,0,3,%s,%s,'TEST',%s) RETURNING id""", (g['operation_id'], sid, correlation_id))
        result = audit_integrity()
        match = next((x for x in result['DUPLICATE_QUANTITY_MOVEMENT'] if x['correlation_id'] == correlation_id), None)
        assert match is not None
        assert match['occurrence_count'] == 2
    finally:
        # quantity_movements.session_id/operation_id are both ON DELETE SET
        # NULL, so the seeded_factory teardown's DELETE FROM work_sessions
        # would silently orphan these rows (session_id/operation_id -> NULL)
        # instead of removing them -- clean up explicitly by correlation_id.
        with db.cursor() as cur:
            cur.execute('DELETE FROM quantity_movements WHERE correlation_id=%s', (correlation_id,))


def test_duplicate_offline_event_detected(db, seeded_factory):
    g = seeded_factory
    client_event_id = f'AUDIT-CLIENT-{uuid.uuid4().hex[:12]}'
    with db.cursor() as cur:
        # A second row with the same client_event_id would violate the
        # UNIQUE constraint through normal INSERTs -- dropping it here
        # proves the audit catches a bypass, same reasoning as the
        # partial-unique-index test above.
        cur.execute('ALTER TABLE kiosk_client_events DROP CONSTRAINT IF EXISTS kiosk_client_events_client_event_id_key')
    try:
        with db.cursor() as cur:
            for i in range(2):
                cur.execute("""INSERT INTO kiosk_client_events(client_event_id,payload_hash,kiosk_id,local_sequence,event_type)
                    VALUES(%s,'HASH','TEST-KIOSK',%s,'SESSION_START')""", (client_event_id, i))
        result = audit_integrity()
        match = next((x for x in result['DUPLICATE_OFFLINE_EVENT'] if x['client_event_id'] == client_event_id), None)
        assert match is not None
        assert match['occurrence_count'] == 2
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_client_events WHERE client_event_id=%s', (client_event_id,))
            cur.execute('ALTER TABLE kiosk_client_events ADD CONSTRAINT kiosk_client_events_client_event_id_key UNIQUE(client_event_id)')


def test_inactive_kiosk_with_live_status_detected(db):
    device = f'AUDIT-KIOSK-{uuid.uuid4().hex[:10]}'
    with db.cursor() as cur:
        cur.execute("INSERT INTO kiosk_identities(device_uuid,status) VALUES(%s,'DISABLED') RETURNING id", (device,))
        identity_id = cur.fetchone()['id']
        cur.execute("INSERT INTO kiosk_status(device_uuid,last_heartbeat_at) VALUES(%s,CURRENT_TIMESTAMP)", (device,))
    try:
        result = audit_integrity()
        assert any(x['identity_id'] == identity_id for x in result['INACTIVE_KIOSK_WITH_LIVE_STATUS'])
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_status WHERE device_uuid=%s', (device,))
            cur.execute('DELETE FROM kiosk_identities WHERE id=%s', (identity_id,))


def test_clean_database_slice_has_no_violations_from_seeded_factory(db, seeded_factory):
    # The factory graph itself (one employee, one OPEN-free operation, no
    # sessions yet) must never trip any category -- a sanity check that
    # these queries aren't over-broad and flagging normal data.
    result = audit_integrity()
    g = seeded_factory
    for category, items in result.items():
        for item in items:
            assert item.get('employee_id') != g['employee_id'], (category, item)
