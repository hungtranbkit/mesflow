"""Production Overview hotfix (2026-09-26): each Operation row names who is
running it right now, from OPEN sessions, grouped per (operation, employee).

Pure grouping tests (no PostgreSQL) + a static contract on the page/SQL.
The real-database behaviour is covered by
tests/integration/test_overview_active_workers.py (real DB)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mesflow.db.repositories import analytics
from mesflow.db.repositories.analytics import _group_active_workers

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)


def _s(session_id, operation_id, employee_id, name, minutes=0, **kw):
    row = dict(session_id=session_id, session_operation_id=operation_id, operation_id=operation_id,
               is_setup=False, employee_id=employee_id, employee_no=f'NV{employee_id:03d}',
               employee_name=name, started_at=T0 + timedelta(minutes=minutes), station_code=None)
    row.update(kw)
    return row


def test_zero_open_sessions_maps_to_nothing():
    assert _group_active_workers([]) == {}
    assert _group_active_workers(None) == {}


def test_one_worker_on_one_operation():
    out = _group_active_workers([_s(1, 10, 7, 'An', station_code='ST-1')])
    assert list(out) == [10]
    (w,) = out[10]
    assert w['employee_id'] == 7 and w['employee_no'] == 'NV007' and w['name'] == 'An'
    assert w['session_count'] == 1 and w['session_ids'] == [1]
    assert w['station_codes'] == ['ST-1'] and w['setup'] is False
    assert w['started_at'] == T0


def test_multiple_workers_on_one_operation_ordered_by_start():
    out = _group_active_workers([_s(1, 10, 7, 'Bình', minutes=5), _s(2, 10, 8, 'An', minutes=1),
                                 _s(3, 10, 9, 'Chi', minutes=9)])
    assert [w['name'] for w in out[10]] == ['An', 'Bình', 'Chi']


def test_workers_are_mapped_to_their_own_operation_only():
    out = _group_active_workers([_s(1, 10, 7, 'An'), _s(2, 11, 8, 'Bình')])
    assert [w['employee_id'] for w in out[10]] == [7]
    assert [w['employee_id'] for w in out[11]] == [8]


def test_one_employee_with_several_open_sessions():
    # Same Operation twice -> one entry, session_count=2, earliest start kept.
    # A different Operation -> listed there too, independently.
    out = _group_active_workers([
        _s(1, 10, 7, 'An', minutes=8, station_code='ST-2'),
        _s(2, 10, 7, 'An', minutes=2, station_code='ST-1'),
        _s(3, 11, 7, 'An', minutes=4),
    ])
    (w,) = out[10]
    assert w['session_count'] == 2 and sorted(w['session_ids']) == [1, 2]
    assert w['started_at'] == T0 + timedelta(minutes=2)
    assert w['station_codes'] == ['ST-2', 'ST-1']
    (w11,) = out[11]
    assert w11['session_count'] == 1 and w11['session_ids'] == [3]


def test_setup_session_reported_on_parent_operation():
    # The query already resolves a SETUP row's session onto its parent
    # (operation_id=parent); the grouping keeps the flag for the UI tag.
    out = _group_active_workers([_s(1, 10, 7, 'An', session_operation_id=99, is_setup=True),
                                 _s(2, 10, 8, 'Bình')])
    by_id = {w['employee_id']: w for w in out[10]}
    assert by_id[7]['setup'] is True and by_id[8]['setup'] is False


def test_operation_overview_attaches_list_with_one_extra_query(monkeypatch):
    calls = []

    def fake_fetch_all(sql, params=()):
        calls.append(sql)
        if 'ws.id session_id' in sql:
            return [_s(1, 10, 7, 'An'), _s(2, 10, 8, 'Bình', minutes=1)]
        if 'day_sessions' in sql:
            return []
        return [dict(operation_id=10, planned_quantity=100, done_qty=5, open_session_count=2, operation_status='IN_PROGRESS'),
                dict(operation_id=11, planned_quantity=100, done_qty=0, open_session_count=0, operation_status='NOT_STARTED')]

    monkeypatch.setattr(analytics, 'fetch_all', fake_fetch_all)
    monkeypatch.setattr(analytics.DashboardRepository, 'today_activity_by_operation', lambda self: {})
    rows = analytics.DashboardRepository().operation_overview(100)
    assert len(calls) == 2  # operations + open sessions, never per row (today rollup stubbed)
    assert [w['name'] for w in rows[0]['active_worker_list']] == ['An', 'Bình']
    assert rows[0]['active_worker_count'] == 2
    assert rows[1]['active_worker_list'] == [] and rows[1]['active_worker_count'] == 0


def test_active_worker_source_is_open_sessions_and_page_renders_it():
    repo = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
    page = (ROOT / 'app/mesflow/web/static/pages/overview.js').read_text(encoding='utf-8')
    body = repo.split('def active_workers_by_operation', 1)[1].split('def overview', 1)[0]
    assert "ws.status='OPEN'" in body and "reportable_session_sql('ws')" in body
    assert 'parent_operation_id' in body
    assert 'x.active_worker_list' in page
    assert '${activeWorkers(x)||todayWorkers(x)}</div>' in page  # OPEN line wins over today history
    assert 'list.slice(0,3)' in page and '+${rest.length}' in page
