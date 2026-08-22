"""Human-readable presentation layer for "Nhật ký nghiệp vụ" (Business Audit
Trail), for normal production managers -- not developers.

The underlying `audit_logs` data (action code, entity_type/id, details_json,
before_json/after_json) is never rewritten by anything in this module. This
module only *interprets* that existing evidence into:

  human-readable summary  ->  structured changes  ->  raw technical data

Pure by design (no DB access, no Flask): given a raw audit_logs row plus
already-batch-fetched enrichment maps (employees/operations/stations/
sessions -- see `mesflow.db.repositories.analytics.AuditRepository.list()`
for how those are collected without N+1 queries), `present()` returns a
single presentation dict the frontend renders directly. Centralizing the
catalog/diff/enum logic here -- instead of scattered per-page JS switch
statements -- is deliberate (task section 2).

Unknown action codes fall through to a safe generic formatter; the original
action code is always preserved (never hidden) in the technical section.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------
# 1. Action catalog -- action code -> {label, category}
#
# category matches the friendly filter groups (section 13): session,
# quantity, po, operation, calendar, employee, exception, admin.
# ---------------------------------------------------------------------

ACTION_CATALOG: dict[str, dict[str, str]] = {
    'SESSION_STARTED': {'label': 'Bắt đầu Session', 'category': 'session'},
    'SESSION_FINISHED': {'label': 'Kết thúc Session', 'category': 'session'},
    'SESSION_EDIT': {'label': 'Chỉnh sửa Session', 'category': 'session'},
    'SESSION_ADJUST': {'label': 'Điều chỉnh sản lượng Session', 'category': 'quantity'},
    'SESSION_EXCEPTION_WORKFLOW_UPDATE': {'label': 'Xử lý Session bất thường', 'category': 'exception'},
    'EXCEPTION_ACKNOWLEDGED': {'label': 'Xác nhận ngoại lệ', 'category': 'exception'},
    'EXCEPTION_RESOLVED': {'label': 'Giải quyết ngoại lệ', 'category': 'exception'},
    'EXCEPTION_IGNORED': {'label': 'Bỏ qua ngoại lệ', 'category': 'exception'},
    'EXCEPTION_AUTO_IGNORED': {'label': 'Tự động bỏ qua ngoại lệ', 'category': 'exception'},
    'WORK_SHIFTS_REPLACE': {'label': 'Cập nhật lịch làm việc', 'category': 'calendar'},
    'OPERATION_CANCEL': {'label': 'Hủy công đoạn', 'category': 'operation'},
    'PRODUCTION_STATE_RECONCILE': {'label': 'Đối soát sản lượng PO', 'category': 'po'},
    'QC_START': {'label': 'Bắt đầu kiểm QC', 'category': 'operation'},
    'QC_COMPLETE': {'label': 'Hoàn tất kiểm QC', 'category': 'operation'},
    'KIOSK_APPROVE': {'label': 'Duyệt thiết bị kiosk', 'category': 'employee'},
    'KIOSK_STATUS_CHANGE': {'label': 'Đổi trạng thái kiosk', 'category': 'admin'},
    'KIOSK_EVENT_RESOLVE': {'label': 'Xử lý sự kiện kiosk', 'category': 'admin'},
    'KPI_SNAPSHOT': {'label': 'Chốt KPI', 'category': 'admin'},
    'EMPLOYEE_PRODUCTIVITY_WALLBOARD_PUBLISH': {'label': 'Trình chiếu năng suất lên Kiosk', 'category': 'admin'},
    'LOGIN_SUCCESS': {'label': 'Đăng nhập thành công', 'category': 'admin'},
    'LOGIN_FAILED': {'label': 'Đăng nhập thất bại', 'category': 'admin'},
}

CATEGORY_LABELS: dict[str, str] = {
    'session': 'Session', 'quantity': 'Sản lượng', 'po': 'PO', 'operation': 'Công đoạn',
    'calendar': 'Lịch làm việc', 'employee': 'Nhân viên', 'exception': 'Xử lý bất thường', 'admin': 'Quản trị',
}


def action_label(action: str) -> str:
    entry = ACTION_CATALOG.get(action)
    if entry:
        return entry['label']
    # Safe readable fallback for an action code this catalog doesn't know yet
    # (section 2) -- never raise, never show a blank title. The original
    # code is always still visible in the technical detail section.
    words = [w for w in str(action or '').replace('-', '_').split('_') if w]
    return ' '.join(w.capitalize() for w in words) if words else 'Hành động hệ thống'


def action_category(action: str) -> str:
    return ACTION_CATALOG.get(action, {}).get('category', 'admin')


# ---------------------------------------------------------------------
# 2. Field catalog -- snake_case field name -> Vietnamese label
# ---------------------------------------------------------------------

FIELD_LABELS: dict[str, str] = {
    'started_at': 'Thời gian bắt đầu', 'ended_at': 'Thời gian kết thúc',
    'detected_at': 'Thời điểm phát hiện', 'acknowledged_at': 'Thời điểm xác nhận',
    'resolved_at': 'Thời điểm giải quyết', 'ignored_at': 'Thời điểm bỏ qua',
    'auto_ignored_at': 'Thời điểm tự động bỏ qua',
    'good_qty': 'Sản phẩm đạt', 'defect_qty': 'Sản phẩm lỗi', 'rework_qty': 'Lỗi sửa được',
    'status': 'Trạng thái', 'employee_id': 'Nhân viên', 'operation_id': 'Công đoạn',
    'station_id': 'Trạm', 'device_uuid': 'Thiết bị/Kiosk',
    'assigned_to': 'Người xử lý', 'workflow_status': 'Trạng thái xử lý',
    'resolution': 'Kết quả xử lý', 'note': 'Ghi chú', 'reason': 'Lý do',
    'severity': 'Mức độ', 'exception_type': 'Loại bất thường', 'exception_code': 'Loại bất thường',
    'production_order_id': 'Lệnh sản xuất (PO)', 'part_id': 'Part', 'session_id': 'Session',
    'resolved_by': 'Người xử lý', 'row_version': 'Phiên bản dữ liệu',
    'code': 'Mã', 'name': 'Tên', 'anchor_start': 'Giờ bắt đầu', 'anchor_end': 'Giờ kết thúc',
    'cross_midnight': 'Qua đêm', 'target_minutes': 'Thời lượng mục tiêu (phút)',
    'active': 'Đang áp dụng', 'previous_status': 'Trạng thái trước đó',
}


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


# ---------------------------------------------------------------------
# 3. Enum catalog -- namespaced by domain, since the SAME field name
# (e.g. "status") means a different thing on a work_session vs. an
# exception_record. Each specialized presenter below picks its own domain.
# ---------------------------------------------------------------------

ENUM_LABELS: dict[str, dict[str, str]] = {
    'work_session_status': {'OPEN': 'Đang mở', 'CLOSED': 'Đã kết thúc', 'CANCELLED': 'Đã hủy'},
    'operation_status': {
        'PENDING': 'Chưa bắt đầu', 'IN_PROGRESS': 'Đang xử lý', 'COMPLETED': 'Đã hoàn tất',
        'CANCELLED': 'Đã hủy',
    },
    'workflow_status': {'NEW': 'Mới', 'IN_PROGRESS': 'Đang xử lý', 'RESOLVED': 'Đã xử lý', 'IGNORED': 'Đã bỏ qua'},
    # exception_records.status (V67 Exception Center) -- distinct universe
    # from work_session.status even though the column is also named "status".
    'exception_status': {
        'OPEN': 'Cần xử lý', 'ACKNOWLEDGED': 'Đã xác nhận', 'RESOLVED': 'Đã giải quyết',
        'AUTO_IGNORED': 'Tự động bỏ qua', 'MANUAL_IGNORED': 'Đã bỏ qua',
    },
    # session_exception_reviews exception_code (legacy inline workflow).
    'exception_code': {
        'OPEN_TOO_LONG': 'Session mở quá lâu', 'OVERLAP': 'Chồng thời gian với session khác',
        'ZERO_QTY_LONG': 'Đóng session lâu nhưng sản lượng bằng 0',
        'MISSING_STATION': 'Thiếu trạm/kiosk', 'INVALID_TIME': 'Giờ kết thúc trước giờ bắt đầu',
    },
    # exception_records.exception_type (V67 Exception Center) -- reuses the
    # exact Vietnamese wording already shown on the live page
    # (pages/exception-center.js `labels`), so the audit trail and the
    # Exception Center itself never disagree on terminology.
    'exception_type': {
        'LONG_OPEN_SESSION': 'Session mở quá lâu', 'ZERO_QUANTITY_LONG': 'Sản lượng bất thường',
        'MISSING_STATION': 'Thiếu thông tin trạm', 'INVALID_DURATION': 'Thời gian không hợp lệ',
        'OPERATION_COMPLETED_SESSION_OPEN': 'Operation hoàn tất nhưng Session còn mở',
        'EMPLOYEE_SESSION_CONFLICT': 'Session xung đột',
    },
    'resolution': {
        'DATA_CORRECTED': 'Đã chỉnh dữ liệu', 'SESSION_CLOSED': 'Đã đóng Session',
        'VALID_EXCEPTION': 'Trường hợp hợp lệ', 'DUPLICATE_ALERT': 'Cảnh báo trùng', 'OTHER': 'Khác',
    },
    'severity': {'CRITICAL': 'Nghiêm trọng', 'HIGH': 'Cao', 'MEDIUM': 'Trung bình', 'LOW': 'Thấp'},
}


def enum_label(domain: str, value: Any) -> str:
    if value is None or value == '':
        return '—'
    text = str(value)
    return ENUM_LABELS.get(domain, {}).get(text, text)


# ---------------------------------------------------------------------
# 4. Value/diff typing
# ---------------------------------------------------------------------

# Fields that are always internal bookkeeping, never a business-meaningful
# change on their own (section 11: "ignore metadata noise ... unless it is
# itself relevant"). row_version/id churn on every edit; never the story.
_DIFF_IGNORED_FIELDS = {'updated_at', 'id', 'row_version', 'start_request_id', 'finish_request_id'}


def _is_datetime_field(field: str) -> bool:
    return field.endswith('_at')


def _values_equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    return a == b


def diff_fields(old: dict[str, Any] | None, new: dict[str, Any] | None, *,
                 enum_domains: dict[str, str] | None = None,
                 include: set[str] | None = None) -> list[dict[str, Any]]:
    """Generic audit diff formatter (section 11): given `old`/`new` dicts,
    return only the fields that actually changed, each already typed and
    (for enum fields) already translated. `include`, when given, restricts
    the comparison to those field names (e.g. only real work_session
    business columns) so an entity's *shape* changing across versions never
    surfaces as noise.
    """
    old = old or {}
    new = new or {}
    enum_domains = enum_domains or {}
    fields = (set(old) | set(new))
    if include is not None:
        fields &= include
    changes = []
    for field in sorted(fields):
        if field in _DIFF_IGNORED_FIELDS:
            continue
        old_v, new_v = old.get(field), new.get(field)
        if _values_equal(old_v, new_v):
            continue
        if field in enum_domains:
            typ = 'enum'
            old_disp, new_disp = enum_label(enum_domains[field], old_v), enum_label(enum_domains[field], new_v)
        elif _is_datetime_field(field):
            typ = 'datetime'
            old_disp, new_disp = old_v, new_v
        elif isinstance(old_v, bool) or isinstance(new_v, bool):
            typ = 'boolean'
            old_disp = 'Có' if old_v else ('—' if old_v is None else 'Không')
            new_disp = 'Có' if new_v else ('—' if new_v is None else 'Không')
        elif isinstance(old_v, (list, dict)) or isinstance(new_v, (list, dict)):
            typ = 'complex'
            old_disp, new_disp = old_v, new_v
        elif old_v is None or new_v is None:
            typ = 'text'
            old_disp = '—' if old_v is None else old_v
            new_disp = '—' if new_v is None else new_v
        else:
            typ = 'number' if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)) else 'text'
            old_disp, new_disp = old_v, new_v
        changes.append({'field': field, 'label': field_label(field), 'type': typ, 'old': old_disp, 'new': new_disp})
    return changes


# ---------------------------------------------------------------------
# 5. Reference resolution helpers (section 8) -- operate on already
# batch-fetched maps; never query the DB themselves.
# ---------------------------------------------------------------------

def _employee_ref(employees: dict[int, dict], employee_id: Any) -> dict | None:
    if not employee_id:
        return None
    row = employees.get(int(employee_id))
    if not row:
        return None
    return {'id': int(employee_id), 'name': row.get('name') or '', 'employee_no': row.get('employee_no') or ''}


def _operation_ref(operations: dict[int, dict], operation_id: Any) -> dict | None:
    if not operation_id:
        return None
    row = operations.get(int(operation_id))
    if not row:
        return None
    return {'id': int(operation_id), 'name': row.get('name') or '', 'code': row.get('code') or ''}


def _station_ref(stations: dict[int, dict], station_id: Any) -> dict | None:
    if not station_id:
        return None
    row = stations.get(int(station_id))
    if not row:
        return None
    return {'id': int(station_id), 'name': row.get('name') or '', 'code': row.get('code') or ''}


def _session_context(session_row: dict | None, employees: dict, operations: dict, stations: dict) -> dict:
    if not session_row:
        return {}
    ctx = {}
    emp = _employee_ref(employees, session_row.get('employee_id'))
    if emp:
        ctx['employee'] = emp
    op = _operation_ref(operations, session_row.get('operation_id'))
    if op:
        ctx['operation'] = op
    st = _station_ref(stations, session_row.get('station_id'))
    if st:
        ctx['station'] = st
    return ctx


# ---------------------------------------------------------------------
# 6. Per-action presenters
# ---------------------------------------------------------------------

_SESSION_DIFF_FIELDS = {
    'employee_id', 'operation_id', 'station_id', 'status', 'started_at', 'ended_at',
    'good_qty', 'defect_qty', 'rework_qty', 'note', 'device_uuid',
}
_SESSION_ENUM_DOMAINS = {'status': 'work_session_status'}


def _resolve_ref_changes(changes: list[dict], employees: dict, operations: dict, stations: dict) -> None:
    """Upgrade a raw employee_id/operation_id/station_id diff row's
    old/new to resolved names in place (section 8), without a second pass
    over the DB -- reuses the same batch-fetched maps as everything else."""
    resolvers = {'employee_id': (_employee_ref, employees), 'operation_id': (_operation_ref, operations),
                 'station_id': (_station_ref, stations)}
    for change in changes:
        if change['field'] not in resolvers:
            continue
        resolve, table = resolvers[change['field']]
        change['type'] = 'ref'
        old_ref, new_ref = resolve(table, change['old']), resolve(table, change['new'])
        change['old'] = (old_ref or {}).get('name') or (f"#{change['old']}" if change['old'] else '—')
        change['new'] = (new_ref or {}).get('name') or (f"#{change['new']}" if change['new'] else '—')


def _present_session_edit(row: dict, details: dict, *, employees: dict, operations: dict, stations: dict) -> dict:
    session_id = row.get('entity_id') or ''
    old, new = details.get('old') or {}, details.get('new') or {}
    changes = diff_fields(old, new, enum_domains=_SESSION_ENUM_DOMAINS, include=_SESSION_DIFF_FIELDS)
    _resolve_ref_changes(changes, employees, operations, stations)
    context = _session_context(new or old, employees, operations, stations)
    summary = f"{row.get('actor_username') or 'Hệ thống'} đã chỉnh sửa Session #{session_id}"
    return {
        'title': f'Chỉnh sửa Session #{session_id}', 'summary': summary, 'context': context,
        'reason': details.get('reason') or '', 'changes': changes, 'session_id': _to_int(session_id),
        'no_change_note': 'Không có trường nghiệp vụ nào thay đổi.' if not changes else '',
    }


def _present_session_adjust(row: dict, details: dict, *, employees: dict, operations: dict, stations: dict) -> dict:
    session_id = row.get('entity_id') or ''
    summary = f"{row.get('actor_username') or 'Hệ thống'} đã điều chỉnh sản lượng Session #{session_id}"
    fields = ['good_qty', 'defect_qty', 'rework_qty', 'note']
    extra = [{'field': f, 'label': field_label(f), 'value': details.get(f)} for f in fields if details.get(f) not in (None, '')]
    return {
        'title': f'Điều chỉnh sản lượng Session #{session_id}', 'summary': summary,
        'context': {}, 'reason': details.get('reason') or '', 'changes': [], 'extra': extra,
        'session_id': _to_int(session_id),
    }


def _present_session_started_finished(row: dict, action: str, before: dict, after: dict, *,
                                       employees: dict, operations: dict, stations: dict) -> dict:
    session_id = row.get('entity_id') or ''
    verb = 'bắt đầu' if action == 'SESSION_STARTED' else 'kết thúc'
    summary = f"{row.get('actor_username') or 'Hệ thống'} đã {verb} Session #{session_id}"
    changes = diff_fields(before, after, enum_domains=_SESSION_ENUM_DOMAINS, include=_SESSION_DIFF_FIELDS) if before else []
    _resolve_ref_changes(changes, employees, operations, stations)
    context = _session_context(after or before, employees, operations, stations)
    return {
        'title': f'{action_label(action)} #{session_id}', 'summary': summary, 'context': context,
        'reason': '', 'changes': changes, 'session_id': _to_int(session_id),
    }


def _present_exception_workflow_update(row: dict, details: dict, *, employees: dict, operations: dict, stations: dict,
                                        sessions: dict) -> dict:
    items = details.get('items') or []
    workflow_status = details.get('workflow_status') or ''
    actor = row.get('actor_username') or 'Hệ thống'
    verb = {'IN_PROGRESS': 'nhận xử lý', 'RESOLVED': 'hoàn tất xử lý', 'IGNORED': 'bỏ qua'}.get(workflow_status, 'cập nhật xử lý')
    if len(items) <= 1:
        session_id = items[0].get('session_id') if items else ''
        exception_code = items[0].get('exception_code') if items else ''
        summary = f"{actor} đã {verb} Session #{session_id}" if session_id else f"{actor} đã {verb}"
        session_row = sessions.get(_to_int(session_id)) if session_id else None
        context = _session_context(session_row, employees, operations, stations)
        extra = [
            {'field': 'exception_code', 'label': 'Vấn đề', 'value': enum_label('exception_code', exception_code)},
            {'field': 'workflow_status', 'label': 'Trạng thái', 'value': enum_label('workflow_status', workflow_status)},
        ]
        if details.get('assigned_to'):
            extra.append({'field': 'assigned_to', 'label': 'Người xử lý', 'value': details['assigned_to']})
        if details.get('resolution'):
            extra.append({'field': 'resolution', 'label': 'Kết quả xử lý', 'value': enum_label('resolution', details['resolution'])})
        return {
            'title': 'Xử lý Session bất thường', 'summary': summary, 'context': context,
            'reason': details.get('note') or '', 'changes': [], 'extra': extra,
            'session_id': _to_int(session_id) if session_id else None,
            'affected_sessions': [{'session_id': _to_int(session_id), **_session_context(session_row, employees, operations, stations)}] if session_id else [],
        }
    # Bulk update (section 6): summarize the count, then list affected sessions.
    affected = []
    for it in items:
        sid = _to_int(it.get('session_id'))
        session_row = sessions.get(sid) if sid else None
        affected.append({'session_id': sid, 'exception_code': enum_label('exception_code', it.get('exception_code')),
                          **_session_context(session_row, employees, operations, stations)})
    summary = f"Đã cập nhật xử lý {len(items)} Session bất thường"
    extra = [{'field': 'workflow_status', 'label': 'Trạng thái', 'value': enum_label('workflow_status', workflow_status)}]
    if details.get('assigned_to'):
        extra.append({'field': 'assigned_to', 'label': 'Người xử lý', 'value': details['assigned_to']})
    if details.get('resolution'):
        extra.append({'field': 'resolution', 'label': 'Kết quả xử lý', 'value': enum_label('resolution', details['resolution'])})
    return {
        'title': 'Xử lý Session bất thường', 'summary': summary, 'context': {},
        'reason': details.get('note') or '', 'changes': [], 'extra': extra,
        'session_id': None, 'affected_sessions': affected,
    }


_EXCEPTION_RECORD_DIFF_FIELDS = {'status', 'resolved_by', 'row_version'}
_EXCEPTION_RECORD_ENUM_DOMAINS = {'status': 'exception_status'}


def _present_exception_record_transition(row: dict, action: str, before: dict, after: dict, metadata: dict, *,
                                          employees: dict, operations: dict, stations: dict, sessions: dict) -> dict:
    actor = row.get('actor_username') or 'Hệ thống'
    verb = {'EXCEPTION_ACKNOWLEDGED': 'xác nhận', 'EXCEPTION_RESOLVED': 'giải quyết',
            'EXCEPTION_IGNORED': 'bỏ qua', 'EXCEPTION_AUTO_IGNORED': 'tự động bỏ qua'}.get(action, 'cập nhật')
    ref = after or before or {}
    exception_id = row.get('entity_id') or ''
    session_id = metadata.get('session_id') or ref.get('session_id')
    summary = f"{actor} đã {verb} ngoại lệ" + (f" (Session #{session_id})" if session_id else f" #{exception_id}")
    session_row = sessions.get(_to_int(session_id)) if session_id else None
    context = _session_context(session_row, employees, operations, stations)
    changes = diff_fields(before, after, enum_domains=_EXCEPTION_RECORD_ENUM_DOMAINS, include=_EXCEPTION_RECORD_DIFF_FIELDS)
    extra = []
    if ref.get('exception_type'):
        extra.append({'field': 'exception_type', 'label': 'Vấn đề', 'value': enum_label('exception_type', ref['exception_type'])})
    if ref.get('severity'):
        extra.append({'field': 'severity', 'label': 'Mức độ', 'value': enum_label('severity', ref['severity'])})
    return {
        'title': action_label(action), 'summary': summary, 'context': context,
        'reason': metadata.get('reason') or '', 'changes': changes, 'extra': extra,
        'session_id': _to_int(session_id) if session_id else None,
    }


def _present_work_shifts_replace(row: dict, details: dict) -> dict:
    items = details.get('items') or []
    actor = row.get('actor_username') or 'Hệ thống'

    def fmt_minute(m):
        m = int(m or 0)
        return f'{(m // 60) % 24:02d}:{m % 60:02d}'

    shifts = []
    for it in items:
        intervals = it.get('intervals') or []
        work = [iv for iv in intervals if str(iv.get('interval_type')).upper() == 'WORK']
        span = ''
        if work:
            start = min(int(iv.get('start_minute', 0)) for iv in work)
            end = max(int(iv.get('end_minute', 0)) for iv in work)
            # fmt_minute already wraps past midnight (% 24) -- a NIGHT shift
            # whose last WORK interval ends at minute 1620 (= 03:00 the next
            # day, the schema's own cross-midnight convention) must display
            # as 03:00, not be capped back down to 00:00.
            span = f"{fmt_minute(start)} – {fmt_minute(end)}"
        shifts.append({
            'code': it.get('code') or '', 'name': it.get('name') or it.get('code') or '',
            'span': span, 'active': it.get('active', True),
        })
    return {
        'title': 'Cập nhật lịch làm việc', 'summary': f'{actor} đã cập nhật cấu hình ca làm việc',
        'context': {}, 'reason': '', 'changes': [], 'shifts': shifts,
    }


def _present_generic(row: dict, action: str, details: dict, *, employees: dict, operations: dict, stations: dict) -> dict:
    """Fallback for any action code without a bespoke presenter above --
    still no raw snake_case dumping: every visible key is label-translated
    and the value formatted, just without a hand-crafted sentence."""
    actor = row.get('actor_username') or 'Hệ thống'
    entity = row.get('entity_type') or ''
    entity_id = row.get('entity_id') or ''
    summary = f"{actor} đã thực hiện {action_label(action).lower()}"
    if entity and entity_id:
        summary += f" ({entity} #{entity_id})"
    extra = []
    for key, value in (details or {}).items():
        # 'reason' already gets its own dedicated section below -- never
        # repeat it a second time as a generic key/value line too.
        if key in ('old', 'new', 'items', 'reason') or value in (None, '', {}, []):
            continue
        if isinstance(value, (dict, list)):
            continue  # complex substructures stay in the technical section only
        extra.append({'field': key, 'label': field_label(key), 'value': value})
    return {
        'title': action_label(action), 'summary': summary, 'context': {},
        'reason': (details.get('reason') or '') if isinstance(details, dict) else '', 'changes': [], 'extra': extra,
    }


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _loads(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    import json
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


# ---------------------------------------------------------------------
# 7. Entry point
# ---------------------------------------------------------------------

def present(row: dict[str, Any], *, employees: dict[int, dict] | None = None,
            operations: dict[int, dict] | None = None, stations: dict[int, dict] | None = None,
            sessions: dict[int, dict] | None = None) -> dict[str, Any]:
    """Build the full presentation payload for one audit_logs row.

    `row` is a raw audit_logs record (dict-like, e.g. a psycopg dict_row) --
    action/entity_type/entity_id/details_json/before_json/after_json/
    actor_username/correlation_id/source/created_at, exactly as stored.
    Never mutates `row`; never touches the database.
    """
    employees = employees or {}
    operations = operations or {}
    stations = stations or {}
    sessions = sessions or {}
    action = row.get('action') or ''
    details = _loads(row.get('details_json'))
    before = _loads(row.get('before_json'))
    after = _loads(row.get('after_json'))

    if action == 'SESSION_EDIT':
        result = _present_session_edit(row, details, employees=employees, operations=operations, stations=stations)
    elif action == 'SESSION_ADJUST':
        result = _present_session_adjust(row, details, employees=employees, operations=operations, stations=stations)
    elif action in ('SESSION_STARTED', 'SESSION_FINISHED'):
        result = _present_session_started_finished(row, action, before, after, employees=employees, operations=operations, stations=stations)
    elif action == 'SESSION_EXCEPTION_WORKFLOW_UPDATE':
        result = _present_exception_workflow_update(row, details, employees=employees, operations=operations, stations=stations, sessions=sessions)
    elif action in ('EXCEPTION_ACKNOWLEDGED', 'EXCEPTION_RESOLVED', 'EXCEPTION_IGNORED', 'EXCEPTION_AUTO_IGNORED'):
        result = _present_exception_record_transition(row, action, before, after, details, employees=employees,
                                                        operations=operations, stations=stations, sessions=sessions)
    elif action == 'WORK_SHIFTS_REPLACE':
        result = _present_work_shifts_replace(row, details)
    else:
        result = _present_generic(row, action, details, employees=employees, operations=operations, stations=stations)

    result.setdefault('category', action_category(action))
    result.setdefault('context', {})
    result.setdefault('changes', [])
    result.setdefault('extra', [])
    result.setdefault('reason', '')
    return result
