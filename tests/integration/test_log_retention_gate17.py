"""Reliability Validation Round 2, Gate 17 -- real, live coverage for
mesflow.core.log_retention.preview()/run() against actual PostgreSQL.

Real confirmed bug found live (2026-08-26): the existing test suite
(test_log_retention_v65838.py) only ever checked the SOURCE TEXT of
log_retention.py/its migration/its cron scripts -- preview()/run() had
NEVER actually been invoked against a real database anywhere. The
'security' policy's ILIKE pattern ("path ILIKE '/api/auth/%'") had its
literal '%' unescaped for psycopg's %-style parameter substitution:
EVERY call crashed with "only '%s','%b','%t' are allowed as placeholders,
got '%'" the moment it reached this (the first) policy. If this ran
unmodified via the nightly cron in production, log_retention would have
failed silently every single night, forever -- exactly the "log/DB-record
growth is unbounded because retention never actually runs" failure mode
Gate 17 exists to catch. Fixed by escaping the literal percent as '%%'.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from mesflow.core.log_retention import preview, run

pytestmark = pytest.mark.postgres


def _insert_action_log(db, *, trace_id, http_status=200, outcome='SUCCESS', path='/api/x', age_days=0):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO action_logs(trace_id,actor_username,actor_role,source_type,method,path,endpoint,action_name,http_status,duration_ms,outcome,created_at)
            VALUES(%s,'test','','web','GET',%s,'x','x',%s,10,%s,%s) RETURNING id""",
            (trace_id, path, http_status, outcome, datetime.now(timezone.utc) - timedelta(days=age_days)))
        return cur.fetchone()['id']


def test_preview_and_run_execute_without_crashing_against_real_db(db):
    # The bare fact that this doesn't raise is itself the regression test
    # for the confirmed '%' escaping bug -- every category's query used to
    # crash on the very first call.
    before = preview()
    assert isinstance(before, dict) and 'action_logs' in before and 'error_traces' in before
    result = run(dry_run=True)
    assert result['dry_run'] is True


def test_security_policy_matches_and_deletes_old_auth_path_rows(db):
    suffix = uuid.uuid4().hex[:10]
    old_id = _insert_action_log(db, trace_id=f'G17-SEC-OLD-{suffix}', http_status=401, outcome='FAILED', path='/api/auth/login', age_days=400)
    new_id = _insert_action_log(db, trace_id=f'G17-SEC-NEW-{suffix}', http_status=401, outcome='FAILED', path='/api/auth/login', age_days=0)
    try:
        result = run(dry_run=False)
        assert result['action_deleted'] >= 1
        with db.cursor() as cur:
            cur.execute('SELECT id FROM action_logs WHERE id=%s', (old_id,))
            assert cur.fetchone() is None, 'old /api/auth/* row past retention must be deleted'
            cur.execute('SELECT id FROM action_logs WHERE id=%s', (new_id,))
            assert cur.fetchone() is not None, 'recent row must survive'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM action_logs WHERE id=ANY(%s)', ([old_id, new_id],))


def test_success_policy_deletes_only_rows_past_its_own_retention_window(db):
    suffix = uuid.uuid4().hex[:10]
    old_id = _insert_action_log(db, trace_id=f'G17-SUC-OLD-{suffix}', path='/api/dashboard', age_days=400)
    new_id = _insert_action_log(db, trace_id=f'G17-SUC-NEW-{suffix}', path='/api/dashboard', age_days=1)
    try:
        run(dry_run=False)
        with db.cursor() as cur:
            cur.execute('SELECT id FROM action_logs WHERE id=%s', (old_id,))
            assert cur.fetchone() is None
            cur.execute('SELECT id FROM action_logs WHERE id=%s', (new_id,))
            assert cur.fetchone() is not None
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM action_logs WHERE id=ANY(%s)', ([old_id, new_id],))


def test_run_records_its_own_history_row(db):
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM log_retention_runs')
        before = cur.fetchone()['n']
    result = run(dry_run=False)
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM log_retention_runs')
        after = cur.fetchone()['n']
    assert after == before + 1
    with db.cursor() as cur:
        cur.execute('SELECT dry_run, finished_at FROM log_retention_runs WHERE id=%s', (result['run_id'],))
        row = cur.fetchone()
    assert row['dry_run'] is False
    assert row['finished_at'] is not None
