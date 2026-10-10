"""Report datasets: thin adapters over the EXISTING authorized report queries.

No dataset owns SQL. Each loader calls the same ReportRepository method the
screen (and the existing Excel/print export) already calls, with the same
filters, then lays the rows out as a neutral ReportDocument. That is what
keeps the numbers in a generated XLSX/PDF identical to the dashboard.

Adding a dataset = one DatasetSpec entry + a loader. Never build SQL from
user/AI text here; filters are typed fields of schema.ReportRequest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from mesflow.reporting.schema import FILTER_LABELS, ReportRequest
from mesflow.web.productivity_excel import SORT_FIELDS as PRODUCTIVITY_SORT_KEYS

# Column kinds understood by both renderers.
TEXT, INT, NUMBER, PERCENT, DURATION, DATETIME, DATE = 'text', 'int', 'number', 'percent', 'duration', 'datetime', 'date'


@dataclass
class Column:
    key: str
    label: str
    kind: str = TEXT
    width: int = 12


@dataclass
class Section:
    title: str
    sheet_name: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None = None
    facts: list[tuple[str, str]] = field(default_factory=list)
    page_break: bool = True


@dataclass
class ReportDocument:
    dataset: str
    title: str
    metadata: dict[str, Any]
    kpis: list[tuple[str, Any, str]]
    sections: list[Section]
    warnings: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.sections[0].rows) if self.sections else 0


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    title: str
    permission: str
    filters: frozenset[str]
    loader: Callable[[ReportRequest, Any], tuple[ReportDocument, dict[str, Any]]]
    roles: frozenset[str] | None = None  # extra literal-role gate, mirrors the screen's own route
    sort_keys: frozenset[str] = frozenset()
    description: str = ''


def _sum(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(r.get(key) or 0) for r in rows)


def _isum(rows: list[dict[str, Any]], key: str) -> int:
    return int(sum(int(r.get(key) or 0) for r in rows))


# --------------------------------------------------------- employee productivity
_EP_SUMMARY_COLS = [
    Column('stt', 'STT', INT, 6), Column('employee_code', 'Mã NV', TEXT, 12),
    Column('employee_name', 'Nhân viên', TEXT, 24), Column('department', 'Bộ phận', TEXT, 16),
    Column('team', 'Nhóm', TEXT, 14), Column('completed_sessions', 'Phiên hoàn tất', INT, 12),
    Column('completed_valid_sessions', 'Phiên hợp lệ', INT, 12),
    Column('productivity_percent', 'Năng suất TB (%)', PERCENT, 14),
    Column('good_qty', 'Sản lượng đạt', INT, 13), Column('defect_qty', 'Lỗi', INT, 9),
    Column('worked_seconds', 'Tổng thời gian', DURATION, 14),
]
_EP_SESSION_COLS = [
    Column('stt', 'STT', INT, 6), Column('work_date', 'Ngày', DATE, 11), Column('po_code', 'PO', TEXT, 14),
    Column('part_label', 'Part', TEXT, 20), Column('operation_code', 'Mã OP', TEXT, 14),
    Column('operation_name', 'Operation', TEXT, 22), Column('started_at', 'Bắt đầu', DATETIME, 16),
    Column('ended_at', 'Kết thúc', DATETIME, 16), Column('actual_seconds', 'Thời gian thực tế', DURATION, 13),
    Column('good_qty', 'Đạt', INT, 9), Column('defect_qty', 'Lỗi', INT, 8),
    Column('standard_seconds_per_unit', 'Định mức (giây/SP)', NUMBER, 11),
    Column('expected_seconds', 'Thời gian định mức', DURATION, 13),
    Column('completion_percent', '% năng suất', PERCENT, 11),
    Column('status_note', 'Trạng thái / ghi chú', TEXT, 30), Column('session_id', 'Mã phiên', INT, 9),
]


def _part_label(s: dict[str, Any]) -> str:
    code = str(s.get('part_code') or '').strip()
    name = str(s.get('part_name') or '').strip()
    return f'{code} · {name}' if code and name and name != code else (code or name)


def _avg_pct(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def load_employee_productivity(req: ReportRequest, repo) -> tuple[ReportDocument, dict[str, Any]]:
    # Same data path as GET /api/reports/employee-productivity/export.xlsx
    # and /print: parse -> load_export_data (2 queries, screen filters).
    from mesflow.web.productivity_excel import session_status_note
    from mesflow.web.productivity_export import load_export_data

    data = load_export_data({
        'from': req.date_from.isoformat() if req.date_from else None,
        'to': req.date_to.isoformat() if req.date_to else None,
        'employee_id': req.employee_id, 'department': req.department, 'team': req.team,
        'search': req.search or '', 'sort': req.sort or 'productivity_percent', 'dir': req.dir or 'desc',
    }, repo)
    employees = [dict(row, stt=i) for i, row in enumerate(data['employees'], 1)]
    totals = {
        'employee_name': f'Tổng cộng ({len(employees)} nhân viên)',
        'completed_sessions': _isum(employees, 'completed_sessions'),
        'completed_valid_sessions': _isum(employees, 'completed_valid_sessions'),
        # Same as the existing "Năng suất TB theo bộ lọc": mean of employee %.
        'productivity_percent': _avg_pct(employees, 'productivity_percent'),
        'good_qty': _isum(employees, 'good_qty'), 'defect_qty': _isum(employees, 'defect_qty'),
        'worked_seconds': _isum(employees, 'worked_seconds'),
    }
    sections = [Section('Tổng hợp năng suất nhân viên', 'Tổng hợp', _EP_SUMMARY_COLS, employees, totals, page_break=False)]
    for group in data['groups']:
        emp = group['employee']
        rows = []
        for i, s in enumerate(group['sessions'], 1):
            row = dict(s, stt=i, part_label=_part_label(s), status_note=session_status_note(s))
            row['standard_seconds_per_unit'] = float(s.get('standard_seconds_per_unit') or 0) or None
            row['expected_seconds'] = s.get('expected_seconds') or None
            rows.append(row)
        pct = emp.get('productivity_percent')
        sections.append(Section(
            f"{emp.get('employee_code') or ''} · {emp.get('employee_name') or ''}",
            ' '.join(x for x in (str(emp.get('employee_code') or ''), str(emp.get('employee_name') or '')) if x) or 'NV',
            _EP_SESSION_COLS, rows,
            {'operation_name': f'Tổng ({len(rows)} phiên)', 'actual_seconds': _sum(rows, 'actual_seconds'),
             'good_qty': _isum(rows, 'good_qty'), 'defect_qty': _isum(rows, 'defect_qty'),
             'completion_percent': _avg_pct(rows, 'completion_percent')},
            facts=[('Bộ phận', emp.get('department') or '—'),
                   ('Phiên hoàn tất', str(int(emp.get('completed_sessions') or 0))),
                   ('Năng suất TB', f'{float(pct):.1f}%' if pct is not None else '—')]))
    kpis = [('Nhân viên', len(employees), INT), ('Phiên hoàn tất', totals['completed_sessions'], INT),
            ('Năng suất TB', totals['productivity_percent'], PERCENT),
            ('Sản lượng đạt', totals['good_qty'], INT), ('Lỗi', totals['defect_qty'], INT)]
    warnings = ['Vượt giới hạn số dòng chi tiết; hãy thu hẹp khoảng ngày.'] if data.get('truncated') else []
    resolved = {'date_from': data.get('date_from'), 'date_to': data.get('date_to')}
    doc = ReportDocument('employee_productivity', 'BÁO CÁO NĂNG SUẤT NHÂN VIÊN', {}, kpis, sections, warnings)
    return doc, resolved


# ------------------------------------------------------------------ work sessions
WORK_SESSION_LIMIT = 10000
_WS_COLS = [
    Column('stt', 'STT', INT, 6), Column('session_id', 'Mã phiên', INT, 9),
    Column('started_at', 'Bắt đầu', DATETIME, 16), Column('ended_at', 'Kết thúc', DATETIME, 16),
    Column('employee_code', 'Mã NV', TEXT, 11), Column('employee_name', 'Nhân viên', TEXT, 20),
    Column('po_code', 'PO', TEXT, 14), Column('part_label', 'Part', TEXT, 18),
    Column('operation_code', 'Mã OP', TEXT, 14), Column('operation_name', 'Operation', TEXT, 20),
    Column('station_code', 'Trạm', TEXT, 10), Column('status_label', 'Trạng thái', TEXT, 12),
    Column('good_qty', 'Đạt', INT, 8), Column('defect_qty', 'Lỗi', INT, 8), Column('rework_qty', 'Sửa', INT, 8),
    Column('duration_seconds', 'Thời lượng', DURATION, 12),
    Column('work_duration_seconds', 'Thời gian làm việc', DURATION, 13),
    Column('note_text', 'Ghi chú', TEXT, 28),
]
_WS_BY_EMPLOYEE_COLS = [
    Column('stt', 'STT', INT, 6), Column('employee_code', 'Mã NV', TEXT, 12),
    Column('employee_name', 'Nhân viên', TEXT, 24), Column('sessions', 'Số phiên', INT, 10),
    Column('good_qty', 'Đạt', INT, 10), Column('defect_qty', 'Lỗi', INT, 10), Column('rework_qty', 'Sửa', INT, 10),
    Column('duration_seconds', 'Thời lượng', DURATION, 13),
    Column('work_duration_seconds', 'Thời gian làm việc', DURATION, 14),
]
_STATUS_LABELS = {'OPEN': 'Đang làm', 'CLOSED': 'Đã kết thúc'}


def _ws_totals(rows: list[dict[str, Any]], label_key: str, label: str) -> dict[str, Any]:
    return {label_key: label, 'good_qty': _isum(rows, 'good_qty'), 'defect_qty': _isum(rows, 'defect_qty'),
            'rework_qty': _isum(rows, 'rework_qty'), 'duration_seconds': _isum(rows, 'duration_seconds'),
            'work_duration_seconds': _isum(rows, 'work_duration_seconds')}


def load_work_sessions(req: ReportRequest, repo) -> tuple[ReportDocument, dict[str, Any]]:
    # Same query as GET /api/session-management (the Phiên làm việc screen).
    from mesflow.core.time_policy import business_date

    end = req.date_to or business_date()
    start = req.date_from or (end.replace(day=1) if not req.date_to else end - timedelta(days=30))
    report = repo.session_management(req.po_id, req.part_id, req.operation_id, req.employee_id, req.status,
                                     start.isoformat(), end.isoformat(), WORK_SESSION_LIMIT)
    items = report.get('items') or []
    rows = []
    for i, s in enumerate(items, 1):
        notes = [str(s.get('note') or '').strip(), str(s.get('close_reason') or '').strip()]
        if s.get('closed_by_system'):
            notes.append('Hệ thống tự đóng')
        if s.get('excluded_from_reports'):
            notes.append(f"Loại khỏi báo cáo: {s.get('exclusion_reason') or ''}".strip())
        rows.append(dict(s, stt=i, part_label=_part_label(s),
                         status_label=_STATUS_LABELS.get(str(s.get('status') or ''), str(s.get('status') or '')),
                         note_text=' · '.join(x for x in notes if x)))
    by_emp: dict[Any, dict[str, Any]] = {}
    for r in rows:
        e = by_emp.setdefault(r.get('employee_id'), {
            'employee_code': r.get('employee_code'), 'employee_name': r.get('employee_name'), 'sessions': 0,
            'good_qty': 0, 'defect_qty': 0, 'rework_qty': 0, 'duration_seconds': 0, 'work_duration_seconds': 0})
        e['sessions'] += 1
        for k in ('good_qty', 'defect_qty', 'rework_qty', 'duration_seconds', 'work_duration_seconds'):
            e[k] += int(r.get(k) or 0)
    summary = sorted(by_emp.values(), key=lambda e: (str(e['employee_code'] or ''), str(e['employee_name'] or '')))
    for i, e in enumerate(summary, 1):
        e['stt'] = i
    total = _ws_totals(rows, 'employee_name', f'Tổng cộng ({len(rows)} phiên)')
    sum_totals = dict(_ws_totals(summary, 'employee_name', f'Tổng cộng ({len(summary)} nhân viên)'),
                      sessions=len(rows))
    sections = [
        Section('Tổng hợp theo nhân viên', 'Tổng hợp', _WS_BY_EMPLOYEE_COLS, summary, sum_totals, page_break=False),
        Section('Chi tiết phiên làm việc', 'Chi tiết phiên', _WS_COLS, rows, total),
    ]
    kpis = [('Số phiên', len(rows), INT), ('Nhân viên', len(summary), INT), ('Sản lượng đạt', total['good_qty'], INT),
            ('Lỗi', total['defect_qty'], INT), ('Sửa', total['rework_qty'], INT)]
    warnings = [f'Chỉ lấy {WORK_SESSION_LIMIT} phiên mới nhất; hãy thu hẹp bộ lọc.'] if len(items) >= WORK_SESSION_LIMIT else []
    doc = ReportDocument('work_sessions', 'BÁO CÁO PHIÊN LÀM VIỆC', {}, kpis, sections, warnings)
    return doc, {'date_from': start.isoformat(), 'date_to': end.isoformat()}


DATASETS: dict[str, DatasetSpec] = {
    'employee_productivity': DatasetSpec(
        'employee_productivity', 'Năng suất nhân viên', 'dashboard.view',
        frozenset({'date_from', 'date_to', 'employee_id', 'department', 'team', 'search', 'sort', 'dir'}),
        load_employee_productivity,
        sort_keys=frozenset(PRODUCTIVITY_SORT_KEYS),
        description='Tổng hợp + chi tiết phiên của từng nhân viên (cùng số liệu màn hình Năng suất).'),
    'work_sessions': DatasetSpec(
        'work_sessions', 'Phiên làm việc', 'session.view',
        frozenset({'date_from', 'date_to', 'po_id', 'part_id', 'operation_id', 'employee_id', 'status'}),
        load_work_sessions, roles=frozenset({'admin', 'manager', 'supervisor'}),
        description='Phiên làm việc theo ngày/PO/Part/Operation/nhân viên (cùng số liệu màn hình Phiên làm việc).'),
}


def can_access(spec: DatasetSpec, role: str, has_permission: Callable[[str], bool]) -> bool:
    if spec.roles is not None and str(role or '').strip().lower() not in spec.roles:
        return False
    return bool(has_permission(spec.permission))


def build_document(req: ReportRequest, repo, *, generated_by: str, timezone_name: str,
                   now: datetime | None = None) -> ReportDocument:
    from mesflow.core.time_policy import site_now

    spec = DATASETS[req.dataset]
    doc, resolved = spec.loader(req, repo)
    stamp = site_now(now, timezone_name) if now is None or now.tzinfo else now
    applied = [(FILTER_LABELS[k], str(v)) for k, v in req.filters().items() if k not in ('date_from', 'date_to')]
    doc.metadata = {
        'dataset': spec.key, 'dataset_title': spec.title,
        'date_from': str(resolved.get('date_from') or ''), 'date_to': str(resolved.get('date_to') or ''),
        'timezone': timezone_name, 'generated_at': stamp.strftime('%d/%m/%Y %H:%M'),
        'generated_at_iso': stamp.isoformat(timespec='seconds'), 'generated_by': generated_by,
        'filters': applied, 'row_count': doc.row_count,
    }
    return doc


def as_date(value: Any) -> date | None:
    return value if isinstance(value, date) and not isinstance(value, datetime) else None
