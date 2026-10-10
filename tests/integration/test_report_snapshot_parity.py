"""Real PostgreSQL parity and read-only enforcement on isolated test data."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest

pytestmark = pytest.mark.postgres


def test_snapshot_five_filter_parity_and_scan_refresh(db, api, seeded_factory, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'services/report-assistant'))
    from snapshot_worker import readonly_source, build_reports, build_active
    from snapshot_store import publish, SnapshotSource
    from data import project
    from test_employee_productivity import _insert_session
    g = seeded_factory
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=2)
    db.execute('UPDATE operations SET standard_seconds_per_unit=17.1234 WHERE id=%s', (g['operation_id'],))
    for index, seconds in enumerate((71.49, 181.49, 193.49)):
        start = day + timedelta(days=index // 2, hours=index)
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'snapshot'+str(index),
                        'CLOSED', start, start + timedelta(seconds=seconds), good_qty=index+1)
    with readonly_source() as (repo, fetch):
        value = build_reports(repo, fetch, now)
    publish(tmp_path, 'reports.json', value)
    base = {'report_type': 'productivity', 'from': day.date().isoformat(), 'to': (day + timedelta(days=1)).date().isoformat(),
            'employee_id': g['employee_id'], 'po_id': None, 'operation_id': None}
    def get(path, params):
        response = api.get('http://mesflow-test-api:8080' + path, params=params, timeout=10)
        assert response.status_code == 200, response.status_code
        return response.json()
    cases = [base, {**base, 'to': base['from']}, {**base, 'po_id': g['po_id']},
             {**base, 'operation_id': g['operation_id']}, {**base, 'po_id': g['po_id'], 'operation_id': g['operation_id']}]
    for intent in cases:
        actual = project(intent, SnapshotSource(tmp_path, intent).get)
        expected = project(intent, get)
        assert actual == expected
    for kind in ('planned_actual', 'operation_output', 'po_progress', 'exceptions'):
        intent = {**base, 'report_type': kind, 'po_id': g['po_id']}
        assert project(intent, SnapshotSource(tmp_path, intent).get) == project(intent, get)
    # A scan-like OPEN -> CLOSED change in the disposable DB becomes visible
    # only after background publication, with no question/request rebuilding it.
    opened = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'snapshot-open',
                             'OPEN', now - timedelta(minutes=1))
    with readonly_source() as (repo, fetch):
        before = build_active(repo, datetime.now(timezone.utc))
    assert opened in {row['session_id'] for row in before['sessions']}
    db.execute("UPDATE work_sessions SET status='CLOSED',ended_at=%s,good_qty=9 WHERE id=%s", (now, opened))
    with readonly_source() as (repo, fetch):
        after = build_active(repo, datetime.now(timezone.utc))
        updated = build_reports(repo, fetch, datetime.now(timezone.utc))
    assert opened not in {row['session_id'] for row in after['sessions']}
    today = now.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
    assert any(row['session_id'] == opened and row['good_qty'] == 9 for row in updated['days'][today]['productivity'])


def test_worker_database_rejects_writes_even_with_test_owner_credential(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'services/report-assistant'))
    from snapshot_worker import readonly_source
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with readonly_source() as (_repo, fetch):
            fetch("UPDATE work_sessions SET good_qty=good_qty WHERE false RETURNING id")


def test_real_stale_login_role_is_denied_for_preview_chat_and_download(db, api, monkeypatch, tmp_path):
    import importlib.util
    import threading
    import requests
    from http.server import HTTPServer
    from mesflow.db.repositories.user_repository import UserRepository
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / 'services/report-assistant'))
    from scope_auth import ScopeHandler
    from snapshot_store import publish
    key = 'isolated-scope-test-key-not-a-real-secret'
    monkeypatch.setenv('REPORT_SCOPE_KEY', key)
    server = HTTPServer(('127.0.0.1', 0), ScopeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    spec = importlib.util.spec_from_file_location('report_scope_integration', root / 'services/report-assistant/server.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.BACKEND = 'http://mesflow-test-api:8080'
    module.SCOPE_BACKEND = 'http://127.0.0.1:' + str(server.server_port)
    module.SCOPE_KEY = key
    module.AUDIT = tmp_path / 'audit.jsonl'; module.SNAPSHOT_DIR = tmp_path
    now = datetime.now(timezone.utc); day = now.date().isoformat()
    publish(tmp_path, 'reports.json', {'schema':1,'generated_at':now.isoformat(),'watermark':now.isoformat(),
            'days':{day:{'employees':[],'sessions':[],'productivity':[]}},'pos':{},'operations':{},'exceptions':{}})
    username = 'scope-test-' + str(int(now.timestamp()*1000000))
    users = UserRepository(); user_id = users.create(username, 'Isolated role fixture', 'Test@123456', 'admin', must_change=False)
    try:
        session = requests.Session()
        result = session.post(module.BACKEND+'/api/auth/login',json={'username':username,'password':'Test@123456'},timeout=10)
        assert result.status_code == 200
        client = module.app.test_client(); client.set_cookie('session', session.cookies.get('session'))
        intent = {'report_type':'productivity','from':day,'to':day,'po_id':None,'operation_id':None,'employee_id':None}
        result = client.post('/reports-api/preview',json={'mode':'live','intent':intent})
        assert result.status_code == 200, result.json
        report_id = result.json['id']
        users.update_profile(user_id, 'Isolated role fixture', 'operator', True)
        # Regression reproduction: the original backend still returns the old
        # signed-session role. The private SELECT check must override that claim.
        stale = session.get(module.BACKEND+'/api/auth/me',timeout=10)
        assert stale.status_code == 200 and stale.json()['user']['role'] == 'admin'
        assert client.post('/reports-api/preview',json={'mode':'live','intent':intent}).status_code == 403
        assert client.post('/reports-api/chat-data',json={'intent':intent}).status_code == 403
        assert client.post('/reports-api/export',json={'report_id':report_id,'format':'csv'}).status_code == 403
        assert client.get('/reports-api/active-sessions').status_code == 403
        denied = requests.get(module.SCOPE_BACKEND+'/scope/'+str(user_id),timeout=3)
        assert denied.status_code == 403 and username not in denied.text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        db.execute('DELETE FROM users WHERE id=%s', (user_id,))
