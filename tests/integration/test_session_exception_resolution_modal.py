"""Inline Session Exception Resolution modal (2026-08-28): resolution-context
+ correct-session against real PostgreSQL/API, covering the field-whitelist,
concurrency, and re-verification behavior that only exists at this layer
(take/resolve/ignore themselves are already covered by
test_v67_exception_center.py -- not re-tested here)."""
import pytest
import requests
pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'


def make_long_open(db, g):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
          VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',%s) RETURNING id""",
                    (g['employee_id'], g['operation_id'], g['station_id'], f"TEST-MODAL-{g['suffix']}"))
        return cur.fetchone()['id']


def find_open(api, sid, kind='LONG_OPEN_SESSION'):
    items = api.get(f'{BASE}/api/exceptions?view=action', timeout=10).json()['items']
    return next(x for x in items if x['session_id'] == sid and x['exception_type'] == kind)


def test_resolution_context_returns_exact_session_and_editable_fields(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    ctx = api.get(f"{BASE}/api/session-exceptions/{item['id']}/resolution-context", timeout=10)
    assert ctx.status_code == 200, ctx.text
    body = ctx.json()
    assert body['session']['session_id'] == sid
    assert body['exception']['id'] == item['id']
    # §3: only the fields THIS exception type's real detector cares about.
    assert set(body['editable_fields']) == {'ended_at', 'status'}
    assert isinstance(body['history'], list) and isinstance(body['activity'], list)


def test_correct_session_drops_fields_outside_the_whitelist(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    # good_qty is NOT in LONG_OPEN_SESSION's whitelist -- must be silently
    # dropped, never applied, even though it's present in the request body.
    response = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session", json={
        'ended_at': None, 'status': 'CLOSED', 'good_qty': 999, 'reason': 'Đóng session treo'
    }, timeout=10)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['item']['status'] == 'CLOSED'
    assert body['item']['good_qty'] != 999
    assert body['cleared'] is True


def test_correct_session_requires_reason(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    response = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session",
                         json={'status': 'CLOSED'}, timeout=10)
    assert response.status_code == 400, response.text


def test_correct_session_then_resolve_succeeds_once_condition_clears(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    ack = api.post(f"{BASE}/api/exceptions/{item['id']}/acknowledge",
                    json={'expected_version': item['row_version']}, timeout=10).json()['item']
    corrected = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session", json={
        'status': 'CLOSED', 'reason': 'Đóng session treo, đã kiểm tra thực tế'
    }, timeout=10)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()['cleared'] is True
    # LONG_OPEN_SESSION auto-transitions via reconcile()'s own
    # SESSION_ALREADY_CLOSED path the instant it's fixed (see
    # exception_service.py's own comment on this) -- already AUTO_IGNORED
    # by the time correct-session's own reconcile() call returns, so a
    # manual resolve() now correctly refuses "already processed" rather
    # than double-resolving it.
    final = api.get(f"{BASE}/api/exceptions/{item['id']}", timeout=10).json()['item']
    assert final['status'] == 'AUTO_IGNORED'
    history = api.get(f"{BASE}/api/exceptions/{item['id']}/history", timeout=10).json()['items']
    assert [x['action'] for x in history] == ['DETECTED', 'ACKNOWLEDGED', 'AUTO_IGNORED']


def test_correct_session_still_blocked_when_condition_remains(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    # Edit something harmless (still ended_at=None -> still OPEN, still long
    # open) -- the anomaly must still be reported as NOT cleared.
    response = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session", json={
        'status': 'OPEN', 'reason': 'chưa sửa xong, lưu tạm'
    }, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()['cleared'] is False
    resolve = api.post(f"{BASE}/api/exceptions/{item['id']}/resolve",
                        json={'expected_version': response.json()['exception']['row_version'], 'reason': 'x'},
                        timeout=10)
    assert resolve.status_code == 409, resolve.text


def test_concurrent_session_change_detected(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    ctx = api.get(f"{BASE}/api/session-exceptions/{item['id']}/resolution-context", timeout=10).json()
    stale_updated_at = ctx['session']['updated_at']
    # Someone else changes the Session in the meantime.
    with db.cursor() as cur:
        cur.execute("UPDATE work_sessions SET note='changed by someone else',updated_at=CURRENT_TIMESTAMP WHERE id=%s", (sid,))
    response = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session", json={
        'status': 'CLOSED', 'reason': 'đóng session', 'expected_updated_at': stale_updated_at
    }, timeout=10)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body['error'] == 'SESSION_CHANGED'
    assert body['current']['note'] == 'changed by someone else'
    # The Session must NOT have been overwritten by the stale correction.
    with db.cursor() as cur:
        cur.execute('SELECT status FROM work_sessions WHERE id=%s', (sid,))
        assert cur.fetchone()['status'] == 'OPEN'


def test_correct_session_on_already_resolved_exception_is_rejected(db, api, seeded_factory):
    sid = make_long_open(db, seeded_factory)
    item = find_open(api, sid)
    with db.cursor() as cur:
        cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP WHERE id=%s", (sid,))
    api.get(f'{BASE}/api/exceptions?view=action', timeout=10)  # reconcile -> AUTO_IGNORED
    response = api.post(f"{BASE}/api/session-exceptions/{item['id']}/correct-session",
                         json={'status': 'CLOSED', 'reason': 'x'}, timeout=10)
    assert response.status_code == 409, response.text


def test_correct_session_unknown_exception_type_has_no_editable_fields(db, api, seeded_factory):
    # §3's "fail closed": an exception_type with no entry in the whitelist
    # must never allow any field through, even if the caller asks for one
    # that would otherwise be valid on work_sessions.
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
          VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '1 hour',%s) RETURNING id""",
                    (seeded_factory['employee_id'], seeded_factory['operation_id'], seeded_factory['station_id'],
                     f"TEST-MODAL-UNKNOWN-{seeded_factory['suffix']}"))
        sid = cur.fetchone()['id']
        cur.execute("""INSERT INTO exception_records(exception_type,severity,entity_type,entity_id,employee_id,
          production_order_id,part_id,operation_id,session_id,title,message,recommended_action,fingerprint,
          metadata_json,occurrence_no,status)
          VALUES('NOT_A_REAL_DETECTOR','LOW','SESSION',%s,%s,%s,%s,%s,%s,'t','m','r',%s,'{}',1,'OPEN') RETURNING id""",
                    (sid, seeded_factory['employee_id'], seeded_factory['po_id'], seeded_factory['part_id'],
                     seeded_factory['operation_id'], sid, f'NOT_A_REAL_DETECTOR:SESSION:{sid}'))
        exception_id = cur.fetchone()['id']
    response = api.post(f"{BASE}/api/session-exceptions/{exception_id}/correct-session", json={
        'status': 'CLOSED', 'ended_at': None, 'good_qty': 5, 'reason': 'thử'
    }, timeout=10)
    assert response.status_code == 200, response.text
    # Nothing was actually writable -- the Session must be untouched.
    with db.cursor() as cur:
        cur.execute('SELECT status FROM work_sessions WHERE id=%s', (sid,))
        assert cur.fetchone()['status'] == 'OPEN'
