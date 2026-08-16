"""Redesigned Business Audit Trail (Nhật ký nghiệp vụ), for normal managers.

Pure unit tests for mesflow.domain.audit_presentation -- no DB, no Flask.
Fixtures below mirror the exact shapes the real write call sites produce
(confirmed by reading mesflow/web/execution.py, mesflow/web/analytics.py,
mesflow/db/repositories/exceptions.py) and the real examples from the task:
SESSION_EDIT #577/#580, SESSION_EXCEPTION_WORKFLOW_UPDATE, WORK_SHIFTS_REPLACE.
"""
import json
from pathlib import Path

from mesflow.domain.audit_presentation import (
    ACTION_CATALOG, CATEGORY_LABELS, ENUM_LABELS, FIELD_LABELS,
    action_label, action_category, diff_fields, enum_label, field_label, present,
)

ROOT = Path(__file__).parents[1]
EMPLOYEES = {3: {'name': 'Phạm Xuân Dung', 'employee_no': 'NV003'}}
OPERATIONS = {75: {'name': 'ĐỘT THÂN THÙNG RÁC', 'code': 'OP075'}}


def _row(action, entity_type='', entity_id='', actor='admin', details=None, before=None, after=None):
    return {
        'id': 1, 'action': action, 'entity_type': entity_type, 'entity_id': entity_id,
        'actor_username': actor, 'created_at': '2026-08-12T12:16:00+00:00',
        'correlation_id': '', 'source': '',
        'details_json': json.dumps(details or {}, ensure_ascii=False),
        'before_json': json.dumps(before or {}, ensure_ascii=False),
        'after_json': json.dumps(after or {}, ensure_ascii=False),
    }


# --- section 15: real fixture cases ---------------------------------------

def test_session_edit_577_shows_only_the_one_changed_field():
    row = _row('SESSION_EDIT', 'work_session', '577', details={
        'reason': 'ok',
        'old': {'id': 577, 'employee_id': 3, 'operation_id': 75, 'station_id': None, 'status': 'CLOSED',
                'started_at': '2026-08-09T10:39:07.380249+00:00', 'ended_at': '2026-08-09T11:00:00+00:00',
                'good_qty': 10, 'defect_qty': 1, 'rework_qty': 0, 'note': '', 'updated_at': '2026-08-09T11:00:00+00:00'},
        'new': {'id': 577, 'employee_id': 3, 'operation_id': 75, 'station_id': None, 'status': 'CLOSED',
                'started_at': '2026-08-09T10:39:00+00:00', 'ended_at': '2026-08-09T11:00:00+00:00',
                'good_qty': 10, 'defect_qty': 1, 'rework_qty': 0, 'note': '', 'updated_at': '2026-08-09T11:05:00+00:00'},
    })
    p = present(row, employees=EMPLOYEES, operations=OPERATIONS)
    assert p['title'] == 'Chỉnh sửa Session #577'
    assert p['summary'] == 'admin đã chỉnh sửa Session #577'
    assert p['reason'] == 'ok'
    assert len(p['changes']) == 1
    change = p['changes'][0]
    assert change['field'] == 'started_at' and change['label'] == 'Thời gian bắt đầu'
    assert change['type'] == 'datetime'
    assert change['old'] == '2026-08-09T10:39:07.380249+00:00' and change['new'] == '2026-08-09T10:39:00+00:00'
    # updated_at differs too (11:00 -> 11:05) but must never surface as a business change.
    assert not any(c['field'] == 'updated_at' for c in p['changes'])
    assert p['context']['employee']['name'] == 'Phạm Xuân Dung'
    assert p['context']['operation']['name'] == 'ĐỘT THÂN THÙNG RÁC'


def test_session_edit_580_no_business_field_changed_shows_note_not_diff_noise():
    same = {'id': 580, 'employee_id': 3, 'operation_id': 75, 'station_id': None, 'status': 'CLOSED',
            'started_at': '2026-08-10T08:00:00+00:00', 'ended_at': '2026-08-10T09:00:00+00:00',
            'good_qty': 5, 'defect_qty': 0, 'rework_qty': 0, 'note': 'x', 'updated_at': '2026-08-10T09:05:00+00:00'}
    row = _row('SESSION_EDIT', 'work_session', '580', details={
        'reason': 'no-op correction', 'old': same, 'new': {**same, 'updated_at': '2026-08-10T09:06:00+00:00'},
    })
    p = present(row)
    assert p['changes'] == []
    assert p['no_change_note']


def test_session_exception_workflow_update_single_session():
    row = _row('SESSION_EXCEPTION_WORKFLOW_UPDATE', 'session_exception', 'bulk', details={
        'workflow_status': 'IN_PROGRESS', 'note': '', 'assigned_to': 'admin', 'resolution': '',
        'items': [{'session_id': 572, 'exception_code': 'OPEN_TOO_LONG', 'exception_fingerprint': 'OPEN_TOO_LONG:0'}],
    })
    sessions = {572: {'employee_id': 3, 'operation_id': 75, 'station_id': None}}
    p = present(row, employees=EMPLOYEES, operations=OPERATIONS, sessions=sessions)
    assert p['title'] == 'Xử lý Session bất thường'
    assert p['summary'] == 'admin đã nhận xử lý Session #572'
    values = {e['field']: e['value'] for e in p['extra']}
    assert values['exception_code'] == 'Session mở quá lâu'
    assert values['workflow_status'] == 'Đang xử lý'
    # the raw technical vocabulary must never leak into the normal-view payload
    dump = json.dumps(p, ensure_ascii=False)
    assert 'OPEN_TOO_LONG:0' not in dump
    assert 'exception_fingerprint' not in dump


def test_session_exception_workflow_update_bulk_lists_affected_sessions():
    items = [{'session_id': i, 'exception_code': 'OPEN_TOO_LONG', 'exception_fingerprint': f'OPEN_TOO_LONG:{i}'} for i in range(5)]
    row = _row('SESSION_EXCEPTION_WORKFLOW_UPDATE', 'session_exception', 'bulk', details={
        'workflow_status': 'RESOLVED', 'note': 'batch check', 'assigned_to': 'admin', 'resolution': 'DATA_CORRECTED',
        'items': items,
    })
    p = present(row)
    assert p['summary'] == 'Đã cập nhật xử lý 5 Session bất thường'
    assert len(p['affected_sessions']) == 5
    assert {e['field']: e['value'] for e in p['extra']}['resolution'] == 'Đã chỉnh dữ liệu'


def test_work_shifts_replace_shows_shift_spans_not_raw_json():
    row = _row('WORK_SHIFTS_REPLACE', 'work_shift', 'all', details={'items': [
        {'code': 'DAY', 'name': 'Ca ngày', 'active': True,
         'intervals': [{'interval_type': 'WORK', 'start_minute': 450, 'end_minute': 1020}]},
        {'code': 'NIGHT', 'name': 'Ca tối', 'active': True,
         'intervals': [{'interval_type': 'WORK', 'start_minute': 1080, 'end_minute': 1620}]},
    ]})
    p = present(row)
    assert p['title'] == 'Cập nhật lịch làm việc'
    assert p['summary'] == 'admin đã cập nhật cấu hình ca làm việc'
    spans = {s['code']: s['span'] for s in p['shifts']}
    assert spans['DAY'] == '07:30 – 17:00'
    assert spans['NIGHT'] == '18:00 – 03:00'
    dump = json.dumps(p, ensure_ascii=False)
    assert 'interval_type' not in dump and 'start_minute' not in dump


# --- catalog completeness --------------------------------------------------

def test_every_real_audit_write_call_site_action_is_catalogued():
    """section 2: 'Translate other existing business audit action codes as
    well.' Cross-checked by grepping every AuditRepository().log(...)/
    record_audit(...) call site in the actual codebase for its literal
    action string -- this test fails the day a new call site adds an action
    that was never taught to the catalog."""
    import re
    discovered = set()
    for path in list((ROOT / 'app/mesflow/web').glob('*.py')) + list((ROOT / 'app/mesflow/db/repositories').glob('*.py')):
        text = path.read_text(encoding='utf-8')
        discovered |= set(re.findall(r"AuditRepository\(\)\.log\([^,]+,\s*'([A-Z][A-Z_]+)'", text))
        # record_audit(cur, action='LITERAL', ...) -- exclude the one dynamic
        # call site (action='EXCEPTION_'+action), which a regex can't
        # evaluate; it's added explicitly below instead.
        discovered |= set(re.findall(r"record_audit\([^)]*?action='([A-Z][A-Z_]+)'(?!\s*\+)", text))
    # exceptions.py: record_audit(cur, action='EXCEPTION_'+action, ...) where
    # action comes from ExceptionRepository.transition()'s own `actions`
    # dict values (ACKNOWLEDGED/RESOLVED/IGNORED) -- plus the separate
    # auto-reconcile call site's literal EXCEPTION_AUTO_IGNORED (already
    # caught by the regex above, kept here too for a single source of truth).
    discovered |= {'EXCEPTION_ACKNOWLEDGED', 'EXCEPTION_RESOLVED', 'EXCEPTION_IGNORED', 'EXCEPTION_AUTO_IGNORED'}
    assert discovered, 'expected to discover at least one real action code'
    missing = discovered - set(ACTION_CATALOG)
    assert not missing, f'uncatalogued action codes found in source: {missing}'


def test_generic_presenter_never_shows_reason_twice():
    """Found visually in the Playwright screenshot for LOGIN_FAILED: 'reason'
    used to appear both as the dedicated Lý do line and as a generic
    key/value pair in `extra` -- must only ever appear once."""
    row = _row('LOGIN_FAILED', 'user', '', details={'reason': 'invalid_credentials'})
    p = present(row)
    assert p['reason'] == 'invalid_credentials'
    assert not any(e['field'] == 'reason' for e in p['extra'])


def test_unknown_action_falls_back_to_readable_label_and_keeps_code_visible():
    row = _row('SOME_BRAND_NEW_ACTION', 'widget', '9', details={'note': 'x'})
    p = present(row)
    assert p['title'] == 'Some Brand New Action'
    assert 'brand new action' in p['summary'].lower()
    # the raw code itself is never lost -- callers render row['action'] in
    # the technical section regardless of what present() does with it.
    assert row['action'] == 'SOME_BRAND_NEW_ACTION'


def test_action_category_matches_friendly_filter_taxonomy():
    assert set(CATEGORY_LABELS) == {'session', 'quantity', 'po', 'operation', 'calendar', 'employee', 'exception', 'admin'}
    for code in ACTION_CATALOG:
        assert action_category(code) in CATEGORY_LABELS


# --- field / enum catalog ---------------------------------------------------

def test_task_field_translations_present():
    expected = {
        'started_at': 'Thời gian bắt đầu', 'ended_at': 'Thời gian kết thúc',
        'good_qty': 'Sản phẩm đạt', 'defect_qty': 'Sản phẩm lỗi', 'rework_qty': 'Lỗi sửa được',
        'status': 'Trạng thái', 'employee_id': 'Nhân viên', 'operation_id': 'Công đoạn',
        'station_id': 'Trạm', 'assigned_to': 'Người xử lý', 'workflow_status': 'Trạng thái xử lý',
        'resolution': 'Kết quả xử lý', 'note': 'Ghi chú',
    }
    for field, label in expected.items():
        assert field_label(field) == label


def test_task_enum_translations_present():
    assert enum_label('work_session_status', 'OPEN') == 'Đang mở'
    assert enum_label('work_session_status', 'CLOSED') == 'Đã kết thúc'
    assert enum_label('work_session_status', 'CANCELLED') == 'Đã hủy'
    assert enum_label('workflow_status', 'IN_PROGRESS') == 'Đang xử lý'
    assert enum_label('workflow_status', 'RESOLVED') == 'Đã xử lý'
    assert enum_label('workflow_status', 'IGNORED') == 'Đã bỏ qua'
    assert enum_label('exception_code', 'OPEN_TOO_LONG') == 'Session mở quá lâu'


def test_enum_domains_do_not_collide_status_means_different_things():
    """work_session.status and exception_records.status share a column
    name but a completely different value universe -- OPEN must resolve
    differently depending on which domain is asked."""
    assert enum_label('work_session_status', 'OPEN') == 'Đang mở'
    assert enum_label('exception_status', 'OPEN') == 'Cần xử lý'


def test_unknown_enum_value_falls_back_to_raw_text_not_crash():
    assert enum_label('workflow_status', 'SOMETHING_NEW') == 'SOMETHING_NEW'
    assert enum_label('not_a_real_domain', 'X') == 'X'
    assert enum_label('workflow_status', None) == '—'


# --- diff engine (section 11) ----------------------------------------------

def test_diff_engine_supports_string_number_boolean_null_datetime():
    old = {'a': 'x', 'b': 1, 'c': True, 'd': None, 'started_at': '2026-01-01T00:00:00+00:00'}
    new = {'a': 'y', 'b': 2, 'c': False, 'd': 'now set', 'started_at': '2026-01-02T00:00:00+00:00'}
    changes = {c['field']: c for c in diff_fields(old, new)}
    assert changes['a']['type'] == 'text' and changes['a']['old'] == 'x' and changes['a']['new'] == 'y'
    assert changes['b']['type'] == 'number' and changes['b']['old'] == 1 and changes['b']['new'] == 2
    assert changes['c']['type'] == 'boolean' and changes['c']['old'] == 'Có' and changes['c']['new'] == 'Không'
    assert changes['d']['old'] == '—' and changes['d']['new'] == 'now set'
    assert changes['started_at']['type'] == 'datetime'


def test_diff_engine_ignores_updated_at_and_row_version_noise():
    old = {'updated_at': 't1', 'row_version': 1, 'id': 5, 'real_field': 'a'}
    new = {'updated_at': 't2', 'row_version': 2, 'id': 5, 'real_field': 'a'}
    assert diff_fields(old, new) == []


def test_diff_engine_never_hides_a_real_business_change():
    old = {'good_qty': 10}
    new = {'good_qty': 12}
    changes = diff_fields(old, new)
    assert len(changes) == 1 and changes[0]['field'] == 'good_qty' and changes[0]['old'] == 10 and changes[0]['new'] == 12


def test_diff_engine_include_restricts_to_named_fields():
    old = {'a': 1, 'ignored_extra': 'x'}
    new = {'a': 2, 'ignored_extra': 'y'}
    changes = diff_fields(old, new, include={'a'})
    assert [c['field'] for c in changes] == ['a']


# --- ID enrichment / references (section 8) --------------------------------

def test_reference_resolution_shows_names_not_bare_ids():
    row = _row('SESSION_EDIT', 'work_session', '577', details={
        'reason': '', 'old': {'employee_id': 3, 'operation_id': 75}, 'new': {'employee_id': 3, 'operation_id': 99},
    })
    p = present(row, employees=EMPLOYEES, operations={75: OPERATIONS[75]})
    change = next(c for c in p['changes'] if c['field'] == 'operation_id')
    assert change['type'] == 'ref'
    assert change['old'] == 'ĐỘT THÂN THÙNG RÁC'
    assert change['new'] == '#99'  # unresolved id (not in the batch-fetched map) still shows a stable fallback, never crashes


# --- section 15/16: no raw JSON in the normal-view payload -----------------

def test_normal_view_payload_never_embeds_raw_nested_objects():
    """The `presentation` dict itself -- title/summary/context/changes/extra
    -- is what a normal view renders. Each individual change/extra value
    must be a plain scalar (already formatted) never a raw nested dict/list
    -- that would just be JSON.stringify'd in disguise. Full raw evidence
    stays in row['details_json']/before_json/after_json, technical-section
    only, never inside `presentation`."""
    row = _row('SESSION_EDIT', 'work_session', '577', details={
        'reason': 'ok', 'old': {'good_qty': 1, 'note': 'a'}, 'new': {'good_qty': 2, 'note': 'a'},
    })
    p = present(row, employees=EMPLOYEES, operations=OPERATIONS)
    assert 'presentation' not in p  # present() returns the payload itself, not a wrapper
    for change in p['changes']:
        assert not isinstance(change['old'], (dict, list)) or change['type'] == 'complex'
        assert not isinstance(change['new'], (dict, list)) or change['type'] == 'complex'
    for e in p['extra']:
        assert not isinstance(e['value'], (dict, list))
