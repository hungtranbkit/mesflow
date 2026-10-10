"""Validated report request: the ONLY way parameters reach a dataset.

Every value is parsed into a typed field or rejected with a Vietnamese
message (HTTP 400). Unknown parameters and filters a dataset does not
support are rejected, never silently ignored -- ignoring them would make
the file look filtered while it actually covers the whole factory.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Mapping

FORMATS = ('xlsx', 'pdf', 'html')
MAX_RANGE_DAYS = 366
MAX_TEXT = 120
# Query keys that are transport, not filters.
_CONTROL_KEYS = {'format', 'dataset', 'autoprint'}
INT_FILTERS = ('po_id', 'part_id', 'operation_id', 'employee_id')
TEXT_FILTERS = ('department', 'team', 'search')
SORT_DIRS = ('asc', 'desc')
SESSION_STATUSES = ('OPEN', 'CLOSED')

FILTER_LABELS = {
    'date_from': 'Từ ngày', 'date_to': 'Đến ngày', 'po_id': 'PO', 'part_id': 'Part',
    'operation_id': 'Operation', 'employee_id': 'Nhân viên', 'department': 'Bộ phận',
    'team': 'Nhóm', 'search': 'Tìm nhân viên', 'status': 'Trạng thái', 'sort': 'Sắp xếp', 'dir': 'Chiều',
}
# Public query names -> field names.
_ALIASES = {'from': 'date_from', 'to': 'date_to'}


class ReportValidationError(ValueError):
    """Bad report parameters (-> 400 VALIDATION_ERROR)."""


@dataclass(frozen=True)
class ReportRequest:
    dataset: str
    format: str = 'xlsx'
    date_from: date | None = None
    date_to: date | None = None
    po_id: int | None = None
    part_id: int | None = None
    operation_id: int | None = None
    employee_id: int | None = None
    department: str | None = None
    team: str | None = None
    search: str | None = None
    status: str | None = None
    sort: str | None = None
    dir: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def filters(self) -> dict[str, Any]:
        """Only the filters actually set, in a stable order."""
        out = {}
        for key, value in asdict(self).items():
            if key in ('dataset', 'format', 'extra') or value in (None, ''):
                continue
            out[key] = value.isoformat() if isinstance(value, date) else value
        return out


def _parse_date(name: str, raw: Any) -> date | None:
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ReportValidationError(f'{FILTER_LABELS[name]} phải có dạng YYYY-MM-DD') from None


def _parse_int(name: str, raw: Any) -> int | None:
    text = str(raw or '').strip()
    if not text:
        return None
    if not text.isdigit() or int(text) <= 0 or len(text) > 12:
        raise ReportValidationError(f'{FILTER_LABELS[name]} không hợp lệ')
    return int(text)


def _parse_text(name: str, raw: Any) -> str | None:
    text = ' '.join(str(raw or '').split())
    if not text:
        return None
    if len(text) > MAX_TEXT:
        raise ReportValidationError(f'{FILTER_LABELS[name]} quá dài (tối đa {MAX_TEXT} ký tự)')
    return text


def parse_report_request(dataset: str, args: Mapping[str, Any], *, allowed_filters: set[str] | frozenset[str],
                         sort_keys: set[str] | frozenset[str] = frozenset(), default_format: str = 'xlsx') -> ReportRequest:
    """Turn raw query args into a ReportRequest for `dataset`, which accepts
    only `allowed_filters` (field names, e.g. {'date_from', 'po_id'})."""
    fmt = str(args.get('format') or default_format).strip().lower()
    if fmt not in FORMATS:
        raise ReportValidationError('Định dạng phải là xlsx, pdf hoặc html')
    values: dict[str, Any] = {}
    for raw_key in args.keys():
        key = _ALIASES.get(raw_key, raw_key)
        if raw_key in _CONTROL_KEYS:
            continue
        if key not in FILTER_LABELS:
            raise ReportValidationError(f'Tham số không được hỗ trợ: {str(raw_key)[:40]}')
        raw = args.get(raw_key)
        if raw in (None, ''):
            continue
        if key not in allowed_filters:
            raise ReportValidationError(f'Báo cáo này không hỗ trợ lọc theo {FILTER_LABELS[key]}')
        if key in ('date_from', 'date_to'):
            values[key] = _parse_date(key, raw)
        elif key in INT_FILTERS:
            values[key] = _parse_int(key, raw)
        elif key in TEXT_FILTERS:
            values[key] = _parse_text(key, raw)
        elif key == 'status':
            status = str(raw).strip().upper()
            if status not in SESSION_STATUSES:
                raise ReportValidationError('Trạng thái phải là OPEN hoặc CLOSED')
            values[key] = status
        elif key == 'sort':
            sort = str(raw).strip()
            if sort not in sort_keys:
                raise ReportValidationError('Cột sắp xếp không hợp lệ')
            values[key] = sort
        elif key == 'dir':
            direction = str(raw).strip().lower()
            if direction not in SORT_DIRS:
                raise ReportValidationError('Chiều sắp xếp phải là asc hoặc desc')
            values[key] = direction
    start, end = values.get('date_from'), values.get('date_to')
    if start and end:
        if start > end:
            raise ReportValidationError('Từ ngày phải trước hoặc bằng Đến ngày')
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise ReportValidationError(f'Khoảng ngày tối đa {MAX_RANGE_DAYS} ngày')
    return ReportRequest(dataset=dataset, format=fmt, **values)
