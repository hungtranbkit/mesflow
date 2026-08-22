"""Regression coverage for the ESP32 kiosk OP-scan bug.

Bug: GET /api/lookup?qr=WF|OP|... (the endpoint the ESP32 kiosk firmware
actually calls to validate a scanned Operation QR -- not
/api/kiosk-web/scan, which is the browser demo kiosk and already checked
this) never looked at the Operation's Production Order status. Scanning an
Operation whose PO had already COMPLETED/CANCELLED, or was never Started,
returned ok=True -- the kiosk let the worker proceed to enter quantity, and
the real rejection only ever surfaced (silently -- see esp.ino's offline
sync fix) once the async offline-sync START ran, long after the worker had
moved on and with nothing shown on screen.

Fix: KioskRepositoryLookup.operation() now also returns po_status, and
legacy_lookup() rejects a WF|OP| scan with 409 BUSINESS_CONFLICT when the
PO is not IN_PROGRESS -- the same contract /api/kiosk-web/scan already had.
"""
import pytest

pytestmark = pytest.mark.postgres
BASE_URL = 'http://mesflow-test-api:8080'


def _scan_op(api, g):
    # Matches seeded_factory's INSERT INTO operations(...,qr) VALUES(...,f'WF|OP|TEST-OP-{suffix}').
    return api.get(f'{BASE_URL}/api/lookup', params={'qr': f"WF|OP|TEST-OP-{g['suffix']}"}, timeout=10)


def test_scanning_operation_of_completed_po_is_rejected(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE production_orders SET status='COMPLETED' WHERE id=%s", (g['po_id'],))
    response = _scan_op(api, g)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body['ok'] is False
    assert body['error'] == 'BUSINESS_CONFLICT'


def test_scanning_operation_of_not_started_po_is_rejected(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE production_orders SET status='DRAFT' WHERE id=%s", (g['po_id'],))
    response = _scan_op(api, g)
    assert response.status_code == 409, response.text
    assert response.json()['error'] == 'BUSINESS_CONFLICT'


def test_scanning_operation_of_cancelled_po_is_rejected(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE production_orders SET status='CANCELLED' WHERE id=%s", (g['po_id'],))
    response = _scan_op(api, g)
    assert response.status_code == 409, response.text
    assert response.json()['error'] == 'BUSINESS_CONFLICT'


def test_scanning_operation_of_in_progress_po_still_succeeds(db, api, seeded_factory):
    # seeded_factory's PO is already IN_PROGRESS -- normal-path regression guard.
    g = seeded_factory
    response = _scan_op(api, g)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ok'] is True
    assert body['type'] == 'operation'
    assert body['operation']['id'] == g['operation_id']


def test_unknown_operation_qr_is_still_a_plain_404(api):
    # Not-found must stay 404, not get swept into the new 409 branch.
    response = api.get(f'{BASE_URL}/api/lookup', params={'qr': 'WF|OP|DOES-NOT-EXIST-XYZ'}, timeout=10)
    assert response.status_code == 404, response.text
    assert response.json()['ok'] is False
