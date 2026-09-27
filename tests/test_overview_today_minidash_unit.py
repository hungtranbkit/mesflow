"""Production Overview mini-dashboard (2026-09-26, part 3): unit + static
contract tests (no PostgreSQL).

_attach_today_pace normalisation (weighted So định mức, delta/pace, no
định mức), the SQL shape of the added fields (one grouped query, rework never
in expected, weighted basis = scored CLOSED sessions), and the page contract
for the per-Operation block and the PO "Hôm nay" strip (derived client-side
from the same rows, exact distinct employees, no per-row fetch). Real
database: tests/integration/test_overview_today_minidash.py."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mesflow.db.repositories import analytics
from mesflow.db.repositories.analytics import TODAY_PACE_TOLERANCE_SECONDS, _attach_today, _attach_today_pace

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
REPO = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
PAGE = (ROOT / 'app/mesflow/web/static/pages/overview.js').read_text(encoding='utf-8')
CSS = (ROOT / 'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')


def _row(**kw):
    base = dict(standard_seconds_per_unit=60, work_seconds=9000, expected_seconds=7800.0,
                scored_work_seconds=9000, scored_expected_seconds=7800.0, weighted_session_count=2,
                employee_ids=[9, 3, None, 3])
    base.update(kw)
    return base


def test_weighted_productivity_and_slow_pace():
    t = _attach_today_pace(_row())
    assert t['standard_configured'] is True
    assert t['actual_work_seconds'] == 9000 and t['expected_seconds'] == 7800
    assert t['weighted_productivity_percent'] == 86.7
    assert t['delta_seconds'] == 1200 and t['pace'] == 'SLOW'
    assert t['employee_ids'] == [3, 9]


def test_employee_ids_are_clean_ints():
    # None is dropped, ids are unique and sorted.
    t = _attach_today_pace(_row(employee_ids=[9, 3, None]))
    assert t['employee_ids'] == [3, 9]
    assert _attach_today_pace(_row(employee_ids=None))['employee_ids'] == []


@pytest.mark.parametrize('work,expected,pace', [
    (3600, 3600, 'ON_TARGET'),
    (3600 + TODAY_PACE_TOLERANCE_SECONDS - 1, 3600, 'ON_TARGET'),
    (3600 + TODAY_PACE_TOLERANCE_SECONDS, 3600, 'SLOW'),
    (3600 - TODAY_PACE_TOLERANCE_SECONDS, 3600, 'FAST'),
    (4500, 5400, 'FAST'),
])
def test_pace_tolerance(work, expected, pace):
    t = _attach_today_pace(_row(scored_work_seconds=work, scored_expected_seconds=expected))
    assert t['pace'] == pace and t['delta_seconds'] == work - expected
    assert t['weighted_productivity_percent'] == round(expected / work * 100, 1)


def test_no_standard_never_shows_a_score():
    t = _attach_today_pace(_row(standard_seconds_per_unit=0, expected_seconds=0, scored_expected_seconds=0))
    assert t['standard_configured'] is False
    assert t['weighted_productivity_percent'] is None and t['delta_seconds'] is None and t['pace'] is None
    assert t['actual_work_seconds'] == 9000  # time still shown


def test_no_closed_output_yet_has_no_score():
    t = _attach_today_pace(_row(scored_work_seconds=0, scored_expected_seconds=0, weighted_session_count=0))
    assert t['standard_configured'] is True
    assert t['weighted_productivity_percent'] is None and t['pace'] is None


def test_attach_today_keeps_minidash_fields_and_open_wins():
    today = {10: _attach_today_pace(_row(employee_ids=[7, 8], session_count=2, open_session_count=1,
                                         worker_list=[dict(employee_id=7), dict(employee_id=8)]))}
    row = {'operation_id': 10, 'active_worker_list': [{'employee_id': 7}]}
    _attach_today(row, today)
    assert row['today_state'] == 'RUNNING'
    assert [w['employee_id'] for w in row['today_worker_list']] == [8]
    assert row['today']['employee_ids'] == [7, 8] and row['today']['pace'] == 'SLOW'


def test_today_query_is_still_one_grouped_query_with_new_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(analytics.DashboardRepository, '_calendar_day_context', lambda self, day: {
        'shift_date': day, 'day_start': datetime(2026, 9, 26, tzinfo=timezone.utc),
        'day_end': datetime(2026, 9, 27, tzinfo=timezone.utc), 'intervals': []})

    def fake_fetch_all(sql, params=()):
        calls.append((sql, list(params)))
        return [dict(operation_id=1, employee_count=1, session_count=1, open_session_count=0, good_qty=4,
                     defect_qty=1, rework_qty=1, recorded_session_count=1, work_seconds=600,
                     productivity_percent=50.0, scored_session_count=1, standard_seconds_per_unit=60,
                     last_ended_at=None, first_started_at=None, expected_seconds=300, scored_work_seconds=600,
                     scored_expected_seconds=300, weighted_session_count=1, employee_ids=[5], worker_list=None)]

    monkeypatch.setattr(analytics, 'fetch_all', fake_fetch_all)
    out = analytics.DashboardRepository().today_activity_by_operation()
    assert len(calls) == 1
    t = out[1]
    assert t['weighted_productivity_percent'] == 50.0 and t['pace'] == 'SLOW' and t['delta_seconds'] == 300


def test_sql_contract():
    body = REPO.split('def today_activity_by_operation', 1)[1].split('def overview', 1)[0]
    # expected = định mức × (Đạt + Lỗi) -- rework never enters it.
    assert "COALESCE(o.standard_seconds_per_unit,0)*(COALESCE(ws.good_qty,0)+COALESCE(ws.defect_qty,0)) expected_seconds" in body
    assert 'rework_qty,0)) expected_seconds' not in body
    assert "SUM(s.expected_seconds) FILTER (WHERE s.reported_today)" in body
    # Weighted basis = the sessions _SESSION_COMPLETION_PERCENT_SQL scores.
    assert "(completion_percent IS NOT NULL AND reported_today AND work_seconds>0) in_weighted" in body
    assert "SUM(s.work_seconds) FILTER (WHERE s.in_weighted)" in body
    assert "array_agg(DISTINCT s.employee_id)" in body
    assert "GREATEST(ws.started_at,%s) day_started_at" in body and 'MIN(s.day_started_at) first_started_at' in body
    assert '_attach_today_pace(item)' in body
    # Still the local calendar day + reportable filter, active list OPEN-only.
    assert '_calendar_day_context(business_date(now))' in body and "reportable_session_sql('ws')" in body
    active = REPO.split('def active_workers_by_operation', 1)[1].split('def today_activity_by_operation', 1)[0]
    assert "ws.status='OPEN'" in active


def test_page_contract_operation_block():
    block = PAGE.split('const todayMetrics=', 1)[1].split('const poToday=', 1)[0]
    for key in ('employees', 'sessions', 'span', 'good', 'defect', 'rework', 'time', 'expected', 'productivity', 'delta'):
        assert f"todayM('{key}'" in block, key
    assert "'Sửa được'" in block and "'đang chạy'" in block and "'Chưa có định mức'" in block
    assert 't.weighted_productivity_percent' in block and 't.productivity_percent' not in block
    assert "'Chậm hơn dự kiến'" in PAGE and "'Nhanh hơn dự kiến'" in PAGE and "'Đúng dự kiến'" in PAGE
    assert 'định mức × (Đạt + Lỗi) ÷ thời gian thực tế × 100%' in block
    # Worker status and names live inside the Hôm nay block, with no sibling row.
    assert '</div>${workers}<div class="ov-today-line">' in PAGE
    assert 'const workerRows=x=>' in PAGE
    assert 'x.active_worker_list' in PAGE and 'x.today_worker_list' in PAGE
    assert 'last_ended_at?` ${T(w.last_ended_at)}`' in PAGE
    assert 'activeWorkers(x)||todayWorkers(x)' not in PAGE
    assert 'overview-op-worker-list' in PAGE
    assert 'data-today-metrics' in PAGE
    assert 'const operationRows=' in PAGE and '${todayMetrics(x)}</div>' in PAGE
    assert 'activeWorkers(x)||todayWorkers(x)}</div>' not in PAGE
    assert 'data-open-op="${x.operation_id}"' in PAGE and 'data-op-detail="${x.operation_id}"' in PAGE


def test_page_contract_po_strip():
    strip = PAGE.split('const poToday=', 1)[1].split('\n  const operationRows=', 1)[0]
    # Derived from the same rows: no request, exact distinct employees.
    assert 'fetch(' not in strip and 'api(' not in strip and 'await' not in strip
    assert 'new Set(ts.flatMap(t=>Array.isArray(t.employee_ids)?t.employee_ids:[])' in strip
    assert "t.pace==='SLOW'" in strip and 't.standard_configured' in strip
    assert "sum(std,'scored_expected_seconds')" in strip and "sum(std,'scored_work_seconds')" in strip
    for key in ('employees', 'sessions', 'ops', 'running', 'good', 'defect', 'rework', 'time', 'expected', 'productivity', 'slow'):
        assert f"m('{key}'" in strip, key
    assert '${poToday(x.po_id)}</summary>' in PAGE


def test_css_uses_tokens_only():
    section = CSS.split('Production Overview mini-dashboard (2026-09-26, part 3)', 1)[1].split('\n.repair-plan', 1)[0]
    assert 'border-radius' not in section
    assert '.overview-po-today{grid-column:1/-1' in section
    assert '.ov-today-line{display:flex;flex-wrap:wrap' in CSS
