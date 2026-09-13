"""P0: a business rule may REFUSE a scan; it may not ERASE it.

The bug, as it was reported from the shop floor: an iPhone scans an Operation
QR whose PO has not been started. The camera overlay shows "PO chưa Start" and
nothing else -- no name, no code, no payload. The person holding the phone
cannot tell whether they scanned the wrong label, whether the label was printed
wrong, or whether the machine misread it. Those three have three different
fixes and looked identical on screen.

Two causes, one on each side of the wire, and both are covered here:

  1. SERVER -- /api/kiosk-web/scan had already resolved the row (it read the
     Operation's name to check po_status) and then threw that away, returning
     only the refusal. Fixed by an ADDITIVE `scanned` field; every pre-existing
     field is byte-for-byte unchanged, so ESP v2 and the fixed station cannot
     notice.
  2. BROWSER -- kiosk.js's scan() has its whole body inside one `try`, so ANY
     refusal jumped to a single catch that announced the scan as "Không nhận
     được mã". The catch now announces what WAS resolved and puts the refusal
     on its own line beside it.

And the invariant that must not move while fixing the display: a refused scan
still creates NO session. test_a_refused_scan_never_touches_work_sessions holds
that down with a repository that explodes on any use.

In-process (create_app() + test_client()), fetch_one monkeypatched -- no
PostgreSQL, and deliberately so: this is about the SHAPE of the answer, which
must hold whatever the database happens to contain.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mesflow.web import app as app_module
from mesflow.web import kiosk as kiosk_module

STATIC = Path(__file__).resolve().parents[1] / 'app/mesflow/web/static'
KIOSK_JS = (STATIC / 'kiosk.js').read_text(encoding='utf-8')
CAMERA_JS = (STATIC / 'kiosk-camera.js').read_text(encoding='utf-8')
KIOSK_HTML = (Path(__file__).resolve().parents[1]
              / 'app/mesflow/web/templates/kiosk.html').read_text(encoding='utf-8')

RAW_OP_QR = 'WF|OPID|4242'
RAW_EMP_QR = 'WF|EMP|E-0099'

OPERATION_ROW = {
    'id': 4242, 'code': 'OP20', 'name': 'Tiện tinh mặt bích', 'qr': RAW_OP_QR,
    'status': 'PLANNED', 'plan_qty': 100, 'done_qty': 0, 'defect_qty': 0,
    'operation_type': 'MACHINING', 'requires_setup': False, 'setup_completed_at': None,
    'parent_operation_id': None, 'part_id': 7, 'production_order_id': 3,
    'part_code': 'P-114', 'part_name': 'Mặt bích', 'display_key': 'P-114-OP20',
    'po_code': 'PO-2026-031', 'product': 'Bơm', 'po_status': 'PLANNED',
}


class _ExplodingSessions:
    """Any attribute touch is a failure -- a refused scan must not go near it."""

    def __getattr__(self, name):
        raise AssertionError(f'a refused scan reached WorkSessionRepository.{name}')


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(kiosk_module, 'WorkSessionRepository', _ExplodingSessions)
    app = app_module.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


# --------------------------------------------------------------------------
# SERVER
# --------------------------------------------------------------------------
def test_po_not_started_names_the_operation_it_refused(client, monkeypatch):
    monkeypatch.setattr(kiosk_module, 'resolve_operation_id', lambda qr: 4242)
    monkeypatch.setattr(kiosk_module, 'fetch_one', lambda *a, **k: dict(OPERATION_ROW))

    response = client.post('/api/kiosk-web/scan', json={'qr': RAW_OP_QR})
    body = response.get_json()

    assert response.status_code == 409
    # Unchanged, to the character -- every existing client keeps working.
    assert body['error'] == 'PO_NOT_STARTED'
    assert body['error_code'] == 'PO-001'
    assert 'PO-2026-031' in body['message']
    # New, and the whole point: the refusal now says WHAT was scanned.
    assert body['scanned'] == {
        'kind': 'operation',
        'title': 'Tiện tinh mặt bích',
        'sub': 'P-114-OP20',
    }


def test_a_refused_scan_never_touches_work_sessions(client, monkeypatch):
    """The display fix must not become a business change.

    _ExplodingSessions raises on ANY attribute, so a start() that crept into
    this path -- or any other repository call -- fails loudly instead of
    quietly opening a session against a PO nobody started.
    """
    monkeypatch.setattr(kiosk_module, 'resolve_operation_id', lambda qr: 4242)
    monkeypatch.setattr(kiosk_module, 'fetch_one', lambda *a, **k: dict(OPERATION_ROW))
    assert client.post('/api/kiosk-web/scan', json={'qr': RAW_OP_QR}).status_code == 409


def test_an_inactive_badge_still_says_whose_badge_it_was(client, monkeypatch):
    """Same principle on the employee side: "không tìm thấy nhân viên đang hoạt
    động" without a name makes the supervisor look the badge up by hand."""
    monkeypatch.setattr(kiosk_module, 'resolve_employee_id', lambda qr: 99)
    monkeypatch.setattr(kiosk_module, 'fetch_one', lambda *a, **k: {
        'id': 99, 'employee_no': 'NV-0099', 'name': 'Trần Văn B', 'department': 'Tiện',
        'position': 'Thợ', 'active': False, 'employment_status': 'RESIGNED', 'qr': RAW_EMP_QR})

    body = client.post('/api/kiosk-web/scan', json={'qr': RAW_EMP_QR}).get_json()
    assert body['error_code'] == 'EMP-001'
    assert body['scanned'] == {'kind': 'employee', 'title': 'Trần Văn B', 'sub': 'NV-0099'}


def test_an_unreadable_payload_claims_no_identity(client):
    """No row was resolved, so there is nothing honest to name. `scanned` must
    be ABSENT rather than an empty shell the UI would render as a blank title."""
    body = client.post('/api/kiosk-web/scan', json={'qr': 'NOT-A-MESFLOW-QR'}).get_json()
    assert body['error_code'] == 'SCN-002'
    assert 'scanned' not in body


def test_the_mobile_door_gives_the_identical_refusal(client, monkeypatch):
    """Same _scan_response(), so the phone cannot drift to a different answer.
    401 here (not 200/409) also re-proves the gate on the way past."""
    assert client.post('/api/kiosk-mobile/scan', json={'qr': RAW_OP_QR}).status_code == 401
    source = (Path(__file__).resolve().parents[1]
              / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    assert source.count('def _scan_response') == 1, 'one implementation, not two'


# --------------------------------------------------------------------------
# BROWSER -- read from source: this is markup/flow shape, not a live behavior
# (the live proof is tests/e2e/kiosk-mobile-camera.spec.js).
# --------------------------------------------------------------------------
def test_the_raw_payload_is_kept_before_it_is_trimmed():
    """`trim()` is right for what gets SENT and wrong for what gets SHOWN: the
    displayed string has to be what the label actually carries, trailing
    whitespace and all, or it cannot be compared against the printed label."""
    assert 'const rawQr = String(qr == null ? \'\' : qr);' in KIOSK_JS
    assert 'qr = rawQr.trim();' in KIOSK_JS


def _announce_calls(source: str) -> list[str]:
    """Every announceScan(...) CALL, matched on parentheses.

    Parentheses, not a regex and not braces: the detail objects contain
    `${...}` templates and nested braces, and the error path passes a ternary
    (`announceScan(named ? {...} : {...})`) rather than a single literal. Only
    paren-matching captures all of them. The definition itself is skipped by
    name.
    """
    calls, index = [], 0
    needle = 'announceScan('
    while (index := source.find(needle, index)) != -1:
        if source[max(0, index - 9):index] == 'function ':
            index += len(needle)
            continue
        depth, cursor = 0, index + len(needle) - 1
        while cursor < len(source):
            if source[cursor] == '(':
                depth += 1
            elif source[cursor] == ')':
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        calls.append(source[index:cursor + 1])
        index = cursor
    return calls


def test_every_scan_announcement_carries_the_raw_payload():
    """Not just the error path -- a correct scan is also where someone checks
    that a freshly printed batch of labels encodes what they meant.

    Counted against `ok:`, so the error path's TWO ternary branches both have
    to carry it; containment alone would pass if only one did.
    """
    calls = _announce_calls(KIOSK_JS)
    assert len(calls) >= 5, f'expected every announceScan call site, found {len(calls)}'
    for call in calls:
        assert call.count('raw:rawQr') == call.count('ok:'), \
            f'an announced scan result with no raw payload:\n{call}'


def test_the_error_path_announces_the_identity_first_and_the_refusal_beside_it():
    catch = KIOSK_JS[KIOSK_JS.index('} catch (error) {\n      setError('):]
    catch = catch[:catch.index('finally {')]
    # It reads what the server resolved...
    assert 'error.scanned' in catch
    # ...uses that as the headline...
    assert 'title:named.title' in catch
    # ...and the refusal goes on its OWN field, not over the top of the title.
    assert re.search(r"error:`\$\{code\} · \$\{error\.message", catch)
    # api() has to let `scanned` out of the error in the first place.
    assert 'if (data.scanned) error.scanned = data.scanned;' in KIOSK_JS


def test_the_overlay_has_somewhere_to_put_both():
    for element in ('camera-result-raw', 'camera-result-error'):
        assert f'id="{element}"' in KIOSK_HTML
        assert f"#{element}" in CAMERA_JS


def test_the_payload_is_rendered_as_text_never_as_markup():
    """A QR payload is data someone else printed. `WF|OP|<img onerror=...>` has
    to appear on screen exactly as written, not run."""
    render = CAMERA_JS[CAMERA_JS.index('function renderResult'):]
    render = render[:render.index('\n  }', render.index('resultEl.classList.add'))]
    assert 'resultRaw.textContent = data.raw' in render
    assert 'resultError.textContent = data.error' in render
    # Comments stripped first: the comment RIGHT ABOVE this code explains why
    # innerHTML is banned here, and a substring search would trip over it.
    code = '\n'.join(line for line in render.splitlines()
                     if not line.lstrip().startswith('//'))
    assert 'innerHTML' not in code


def test_the_error_styling_did_not_swallow_the_result_card():
    """data-kind="error" recolours the card; it must not hide the name, the code
    or the payload -- which is exactly what the old single-line card did."""
    css = (STATIC / 'kiosk.css').read_text(encoding='utf-8')
    error_rules = [line for line in css.splitlines()
                   if '.camera-result[data-kind="error"]' in line]
    assert error_rules, 'the error state must still be visually distinct'
    for rule in error_rules:
        assert 'display:none' not in rule
    assert '.camera-result-raw{' in css
    assert '.camera-result-error{' in css
