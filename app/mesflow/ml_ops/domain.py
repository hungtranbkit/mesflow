"""MES session facts, not sensor telemetry or employee performance scores."""
from datetime import datetime
import math
import statistics

FEATURES = ['log_elapsed_seconds', 'log_total_qty', 'defect_fraction']
CONTRACT = 'mesflow-closed-production-session-v1'
MIN_ROWS = 100
TTL = 600


class DataError(ValueError):
    pass


def physical(row):
    values = [row.get(k) for k in ('duration_seconds', 'good_qty', 'defect_qty')]
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1e9 for v in values):
        raise DataError('invalid_session_numbers')
    seconds, good, defect = values
    if seconds <= 0:
        raise DataError('invalid_session_duration')
    total = good + defect
    return [seconds, total, defect / total if total else 0]


def features(row):
    duration, total, fraction = physical(row)
    return [math.log1p(duration), math.log1p(total), fraction]


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.utcoffset() is None:
            raise ValueError()
        return dt.timestamp()
    except (ValueError, TypeError):
        raise DataError('invalid_timestamp') from None


def split(rows):
    if not MIN_ROWS <= len(rows) <= 2000:
        raise DataError('insufficient_or_excess_data')
    if len({r['session_id'] for r in rows}) != len(rows):
        raise DataError('duplicate_session')
    ordered = sorted(rows, key=lambda r: (timestamp(r['ended_at']), r['session_id']))
    for row in ordered:
        features(row)
    cut = int(len(ordered) * .8)
    # Equal timestamps must never straddle the temporal boundary.
    while cut > 0 and timestamp(ordered[cut-1]['ended_at']) == timestamp(ordered[cut]['ended_at']):
        cut -= 1
    if cut < 80 or len(ordered)-cut < 20:
        raise DataError('insufficient_temporal_history')
    return ordered[:cut], ordered[cut:]


def baseline(rows):
    columns = list(zip(*(physical(r) for r in rows)))
    result = []
    for name, unit, values, floor in zip(
            ('elapsed_seconds', 'total_qty', 'defect_fraction'),
            ('seconds', 'units', 'ratio'), columns, (60., 2., .02)):
        median = statistics.median(values)
        mad = statistics.median(abs(v-median) for v in values)
        spread = max(1.4826 * mad, floor)
        result.append(dict(feature=name, unit=unit, median=median, mad=mad,
                           lower=max(0., median-4*spread), upper=median+4*spread))
    return result


def explain(row, reference):
    return [dict(b, observed=value, outside_baseline=not b['lower'] <= value <= b['upper'],
                 explanation=f"{b['feature']}: {value:.3f} {b['unit']}; historical median "
                             f"{b['median']:.3f}, baseline range [{b['lower']:.3f}, {b['upper']:.3f}].")
            for b, value in zip(reference, physical(row))]


def distribution(rows):
    columns = list(zip(*(physical(r) for r in rows)))
    return {name: {'min': min(v), 'median': statistics.median(v),
                   'p95': sorted(v)[math.ceil(.95*len(v))-1], 'max': max(v)}
            for name, v in zip(('elapsed_seconds', 'total_qty', 'defect_fraction'), columns)}
