"""Private precomputed source adapter. No HTTP, SQL, credentials or rebuild path."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

from schema import ReportError

MAX_BYTES = 24 * 1024 * 1024
SCHEMA = 1


def publish(directory, name, value):
    """One atomic replacement; readers see either complete generation."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError('snapshot byte bound exceeded')
    fd, temporary = tempfile.mkstemp(prefix='.' + name, dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(directory, name, ttl):
    try:
        with (Path(directory) / name).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        value = json.loads(raw)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value['generated_at'])).total_seconds()
        if value['schema'] != SCHEMA or not 0 <= age <= ttl:
            raise ValueError()
        return value, {'generated_at': value['generated_at'], 'age_seconds': round(age, 1),
                       'ttl_seconds': ttl, 'stale': False, 'watermark': value['watermark'],
                       'sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError):
        raise ReportError('Ảnh chụp chưa sẵn sàng hoặc đã cũ. Bộ xử lý nền đang cập nhật; hãy thử lại sau.', 503)


def days(start, end):
    current = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while current <= stop:
        yield current.isoformat()
        current += timedelta(days=1)


def employee_cells(rows):
    """Additive sufficient statistics; the existing repository supplies scores."""
    groups = {}
    for row in rows:
        key = str(row['employee_id'])
        cell = groups.setdefault(key, {
            'employee_id': row['employee_id'], 'employee_code': row['employee_code'],
            'employee_name': row['employee_name'], 'completed_sessions': 0,
            'good_qty': Decimal(0), 'defect_qty': Decimal(0), 'seconds': Decimal(0),
            'score_sum': Decimal(0), 'score_count': 0})
        cell['completed_sessions'] += 1
        for target, source in [('good_qty', 'good_qty'), ('defect_qty', 'defect_qty'), ('seconds', 'actual_seconds')]:
            cell[target] += Decimal(str(row.get(source) or 0))
        if row.get('completion_percent') is not None:
            cell['score_sum'] += Decimal(str(row['completion_percent']))
            cell['score_count'] += 1
    return list(groups.values())


class SnapshotSource:
    def __init__(self, directory, intent):
        self.value, self.metadata = load(directory, 'reports.json', 150)
        self.partitions = []
        for day in days(intent['from'], intent['to']):
            partition = self.value['days'].get(day)
            if partition is None:
                raise ReportError('Ngày nằm ngoài phạm vi ảnh chụp đã chuẩn bị. Chọn trong 93 ngày gần nhất.', 422)
            self.partitions.append(partition)

    def get(self, path, params):
        if path.startswith('/api/reports/production-orders/'):
            value = self.value['pos'].get(path.rsplit('/', 1)[1])
            if value is None: raise ReportError('Không tìm thấy PO.', 404)
            return {'report': value}
        if path.startswith('/api/operations/'):
            value = self.value['operations'].get(path.rsplit('/', 1)[1])
            if value is None: raise ReportError('Không tìm thấy Operation.', 404)
            return {'item': value}
        if path == '/api/session-management':
            rows = [row for part in self.partitions for row in part['sessions']]
            for key in ('po_id', 'operation_id', 'employee_id'):
                if params.get(key): rows = [row for row in rows if row[key] == params[key]]
            rows.sort(key=lambda row: (parsedate_to_datetime(row['started_at']), row['session_id']), reverse=True)
            return {'items': rows[:params['limit']]}
        if path.startswith('/api/session-management/'):
            key = path.rsplit('/', 1)[1]
            return {'session': {'session_id': int(key)}, 'exceptions': self.value['exceptions'].get(key, [])}
        if path == '/api/reports/employee-productivity':
            groups = {}
            for part in self.partitions:
                for cell in part['employees']:
                    if params.get('employee_id') and cell['employee_id'] != params['employee_id']: continue
                    target = groups.setdefault(cell['employee_id'], {**cell, **dict.fromkeys(
                        ('completed_sessions', 'good_qty', 'defect_qty', 'seconds', 'score_sum', 'score_count'), Decimal(0))})
                    for key in ('completed_sessions', 'good_qty', 'defect_qty', 'seconds', 'score_sum', 'score_count'):
                        target[key] += Decimal(str(cell[key]))
            rows = []
            for cell in groups.values():
                cell['_sort_score'] = cell['score_sum'] / cell['score_count'] if cell['score_count'] else None
                cell['productivity_percent'] = round(float(cell['score_sum'] / cell['score_count']), 2) if cell['score_count'] else None
                cell['worked_seconds'] = int(cell['seconds'].quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                rows.append(cell)
            rows.sort(key=lambda row: (row['productivity_percent'] is None, -(row['_sort_score'] or 0), row['employee_code']))
            return {'employees': rows[:params['limit']]}
        if path.startswith('/api/reports/employee-productivity/'):
            employee_id = int(path.rsplit('/', 1)[1])
            rows = [row for part in self.partitions for row in part['productivity'] if row['employee_id'] == employee_id]
            rows.sort(key=lambda row: parsedate_to_datetime(row['started_at']), reverse=True)
            # Match the existing detail API's per-session rounding, before the
            # report assistant applies its existing filtered aggregation.
            rows = [{**row, 'completion_percent': round(float(row['completion_percent']), 2)
                     if row['completion_percent'] is not None else None} for row in rows]
            return {'employee': {'employee_id': employee_id}, 'sessions': rows}
        raise ReportError('Nguồn ảnh chụp không được phép.', 400)
