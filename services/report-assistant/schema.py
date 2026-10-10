"""Deterministic report schema and public-only intent extraction. No SQL."""
from datetime import date, datetime, timedelta
import re
import unicodedata
from zoneinfo import ZoneInfo

TYPES = {
    'productivity': ('Năng suất nhân viên', ['nang suat', 'productivity']),
    'po_progress': ('Tiến độ PO', ['tien do', 'po progress']),
    'operation_output': ('Sản lượng Operation', ['san luong', 'operation output']),
    'planned_actual': ('Định mức so với thực tế', ['dinh muc', 'ke hoach', 'thuc te', 'planned', 'actual']),
    'exceptions': ('Ngoại lệ phiên', ['ngoai le', 'bat thuong', 'exception']),
}
FIELDS = {'report_type', 'from', 'to', 'po_id', 'operation_id', 'employee_id'}
PERIODS = {'today', 'yesterday', 'this_week', 'last_week', 'this_month', None}


class ReportError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd')) if not unicodedata.combining(c))


def period_bounds(period, today=None):
    today = today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    start = end = today
    if period == 'yesterday': start = end = today - timedelta(days=1)
    elif period == 'this_week': start = today - timedelta(days=today.weekday())
    elif period == 'last_week':
        end = today - timedelta(days=today.weekday()+1); start = end - timedelta(days=6)
    elif period == 'this_month': start = today.replace(day=1)
    elif period != 'today': return None, None
    return start.isoformat(), end.isoformat()


def extract(text):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
        raise ReportError('Nhập yêu cầu từ 1 đến 500 ký tự.')
    clean = normalize(text)
    # Only these public enum values may be sent to AI, never the raw text/IDs.
    candidates = [key for key, (_, words) in TYPES.items() if any(word in clean for word in words)]
    period = None
    for words, value in [('hom nay', 'today'), ('hom qua', 'yesterday'), ('tuan truoc', 'last_week'), ('tuan nay', 'this_week'), ('thang nay', 'this_month')]:
        if words in clean: period = value; break
    result = dict.fromkeys(FIELDS)
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', clean)
    if dates: result['from'], result['to'] = dates[0], dates[1] if len(dates)>1 else dates[0]
    else: result['from'], result['to'] = period_bounds(period)
    for field, names in [('po_id', 'po'), ('operation_id', 'operation|op'), ('employee_id', 'nhan vien|employee|nv')]:
        match = re.search(r'\b(?:'+names+r')\s*(?:id\s*)?#?\s*(\d+)\b', clean)
        if match: result[field] = int(match.group(1))
    result['report_type'] = candidates[0] if len(candidates) == 1 else None
    return result, candidates, period


def validate(value, complete=True):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ReportError('Chỉ chấp nhận loại báo cáo và bộ lọc đã công bố.')
    result = {key: value.get(key) for key in FIELDS}
    if result['report_type'] not in TYPES:
        raise ReportError('Chọn loại báo cáo cần tạo.')
    for name in ('po_id', 'operation_id', 'employee_id'):
        number = result[name]
        if number is not None and (type(number) is not int or not 1 <= number <= 2147483647):
            raise ReportError('ID phải là số nguyên dương hợp lệ.')
    for key in ('from', 'to'):
        if not result[key] and not complete: continue
        try:
            if not isinstance(result[key], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', result[key]): raise ValueError()
            date.fromisoformat(result[key])
        except (ValueError, TypeError): raise ReportError('Chọn ngày bắt đầu và kết thúc (YYYY-MM-DD).')
    if result['from'] and result['to']:
        span = (date.fromisoformat(result['to']) - date.fromisoformat(result['from'])).days
        if not 0 <= span <= 30: raise ReportError('Khoảng báo cáo phải từ 1 đến 31 ngày.')
    if complete and result['report_type'] == 'po_progress' and not result['po_id']:
        raise ReportError('Tiến độ PO cần chọn ID Production Order.')
    return result
