"""Snapshot lifecycle, precision, privacy and request-time I/O boundaries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_report_assistant import BASE, authenticated, preview, service


def test_warm_queries_and_downloads_never_rebuild_or_read_business_api(service):
    client = authenticated(service)
    first = preview(service, client)
    second = preview(service, client)
    assert first['rows'] == second['rows']
    assert first['generated_at'] == second['generated_at']
    assert first['snapshot']['sha256'] == second['snapshot']['sha256']
    response = client.post('/reports-api/export', json={'report_id': first['id'], 'format': 'csv'})
    assert response.status_code == 200
    assert {path for path, _ in service.calls} == {'/api/auth/me'}


@pytest.mark.parametrize('condition', ['cold', 'stale', 'corrupt', 'future', 'schema'])
def test_cold_stale_corrupt_fail_closed_without_sync_rebuild(service, condition):
    path = service.SNAPSHOT_DIR / 'reports.json'
    value = json.loads(path.read_text())
    if condition == 'cold': path.unlink()
    elif condition == 'corrupt': path.write_text('{')
    else:
        if condition == 'schema': value['schema'] = 999
        else: value['generated_at'] = (datetime.now(timezone.utc) + timedelta(seconds=60 if condition == 'future' else -151)).isoformat()
        path.write_text(json.dumps(value))
    response = authenticated(service).post('/reports-api/preview', json={'mode': 'live', 'intent': BASE})
    assert response.status_code == 503
    assert {p for p, _ in service.calls} == {'/api/auth/me'}
    assert not service.snapshots


def test_refresh_atomic_generation_and_old_download_consistency(service):
    from snapshot_store import publish
    client = authenticated(service)
    first = preview(service, client)
    path = service.SNAPSHOT_DIR / 'reports.json'
    value = json.loads(path.read_text())
    value['days'][BASE['from']]['employees'][0]['good_qty'] = 99
    (service.SNAPSHOT_DIR / '.reports.json-interrupted').write_bytes(b'incomplete')
    publish(service.SNAPSHOT_DIR, 'reports.json', value)
    second = preview(service, client)
    assert second['rows'][0]['good_qty'] == 99
    assert first['rows'][0]['good_qty'] == 12
    assert first['snapshot']['sha256'] != second['snapshot']['sha256']
    response = client.post('/reports-api/export', json={'report_id': first['id'], 'format': 'csv'})
    assert b',12,' in response.data
    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in service.SNAPSHOT_DIR.iterdir()) == ['reports.json']


def test_daily_combination_preserves_unrounded_average_and_seconds(service):
    from snapshot_store import employee_cells, publish, SnapshotSource
    value = json.loads((service.SNAPSHOT_DIR / 'reports.json').read_text())
    rows = [{'employee_id': 7, 'employee_code': 'NV7', 'employee_name': 'Employee',
             'good_qty': 1, 'defect_qty': 0, 'actual_seconds': Decimal('0.49'),
             'completion_percent': Decimal(score)} for score in ('1.0049', '1.0149', '1.0149')]
    value['days'][BASE['from']]['employees'] = employee_cells(rows[:1])
    value['days']['2026-10-02']['employees'] = employee_cells(rows[1:])
    publish(service.SNAPSHOT_DIR, 'reports.json', value)
    source = SnapshotSource(service.SNAPSHOT_DIR, BASE)
    row = source.get('/api/reports/employee-productivity', {'limit': 501})['employees'][0]
    assert row['productivity_percent'] == 1.01  # not rounded-daily average (1.00)
    assert row['worked_seconds'] == 1  # round after sum, not 0 + 1
    assert row['completed_sessions'] == 3


def test_chat_data_auth_revocation_privacy_and_no_ai(service, monkeypatch):
    def forbidden(*args): raise AssertionError('external AI must never receive facts')
    monkeypatch.setattr(service, 'ai_select', forbidden)
    client = authenticated(service)
    response = client.post('/reports-api/chat-data', json={'intent': BASE})
    assert response.status_code == 200
    assert response.json['external_ai_allowed'] is False
    assert response.json['facts']['row_count'] == 1
    assert all(text not in response.text for text in ('HYPERLINK', 'NV-7', 'employee_id', 'rows', 'sql'))
    assert service.app.test_client().post('/reports-api/chat-data', json={'intent': BASE}).status_code == 401
    monkeypatch.setattr(service, 'current_user', lambda required=True: {'id': 1, 'role': 'manager', 'permissions': []})
    assert client.post('/reports-api/chat-data', json={'intent': BASE}).status_code == 403
    assert client.post('/reports-api/preview', json={'mode': 'live', 'intent': BASE}).status_code == 403


def test_active_sessions_private_fresh_counts_and_revoke(service, monkeypatch):
    from snapshot_store import publish
    now = datetime.now(timezone.utc).isoformat()
    publish(service.SNAPSHOT_DIR, 'active.json', {'schema': 1, 'generated_at': now, 'watermark': now,
                                                'sessions': [{'employee_id': 7}, {'employee_id': 7}]})
    client = authenticated(service)
    result = client.get('/reports-api/active-sessions')
    assert result.json['facts'] == {'active_sessions': 2, 'active_employees': 1}
    assert 'employee_id' not in result.text
    assert service.app.test_client().get('/reports-api/active-sessions').status_code == 401
    monkeypatch.setattr(service, 'current_user', lambda required=True: {'id': 1, 'role': 'operator', 'permissions': ['po.view', 'session.view']})
    assert client.get('/reports-api/active-sessions').status_code == 403


def test_pdf_admission_timeout_and_no_unauthorized_renderer(service, monkeypatch):
    client = authenticated(service)
    record = preview(service, client)
    calls = []
    def render(*args, **kwargs):
        calls.append(kwargs)
        raise service.subprocess.TimeoutExpired('renderer', 12)
    monkeypatch.setattr(service.subprocess, 'run', render)
    assert authenticated(service, 'bob').post('/reports-api/export', json={'report_id': record['id'], 'format': 'pdf'}).status_code == 403
    assert not calls
    assert client.post('/reports-api/export', json={'report_id': record['id'], 'format': 'pdf'}).status_code == 503
    assert calls[0]['timeout'] == 12
    assert service.pdf_slots.acquire(blocking=False)
    service.pdf_slots.release()


def test_worker_caps_do_not_replace_last_good_snapshot(service, monkeypatch):
    from snapshot_worker import bounded
    from snapshot_store import publish
    with pytest.raises(ValueError): bounded([1, 2], 2)
    before = (service.SNAPSHOT_DIR / 'reports.json').read_bytes()
    import snapshot_store
    monkeypatch.setattr(snapshot_store, 'MAX_BYTES', 1)
    with pytest.raises(ValueError): publish(service.SNAPSHOT_DIR, 'reports.json', {'oversized': True})
    assert (service.SNAPSHOT_DIR / 'reports.json').read_bytes() == before


def test_old_preview_export_keeps_rows_but_labels_current_source_age(service):
    client = authenticated(service)
    record = preview(service, client)
    stored = service.snapshots[record['id']]
    stored['snapshot']['generated_at'] = (datetime.now(timezone.utc) - timedelta(seconds=160)).isoformat()
    response = client.post('/reports-api/export', json={'report_id': record['id'], 'format': 'csv'})
    assert response.status_code == 200
    import csv, io
    row = next(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
    metadata = json.loads(row['snapshot'])
    assert metadata['stale'] and metadata['age_seconds'] >= 160
    assert row['good_qty'] == '12'
