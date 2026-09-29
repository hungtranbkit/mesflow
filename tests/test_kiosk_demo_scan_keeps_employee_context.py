"""Web kiosk simulator: demo employee scan -> demo OP scan must not SCN-003.

P0 on dev.mesflow.net/kiosk (2026-09-29): with the "Mô phỏng quét QR" panel
open, result screens ('error', 'started') stay pinned (scheduleReset() skips
them while the panel is open, and 'error' never auto-returns). Any scan on
such a screen went through `reset(); setTimeout(() => scan(qr), 50);` --
reset() wiped the employee just identified, the re-scan ran in 'ready', and
every Operation QR was rejected with SCN-003 "Hãy quét thẻ nhân viên trước".
The re-scan also POSTed /scan a second time and left a 'ready' gap that the
next click fell into.

Fix: the simulator buttons scan with `{source:'demo'}`; on a terminal screen
such a scan reuses the result it already has -- an employee resets and is
handled as in 'ready', an Operation continues the operation branch for the
same employee/open-session list, and an Operation with nobody identified
still gets SCN-003. Real scanner / camera / MESFlowKioskDemo.scan keep the
old reset-and-rescan path unchanged.

Behavioral proof (mocked API, fails on the unfixed kiosk.js for D1-D3):
tests/e2e/kiosk-demo-employee-then-op.spec.js.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')


def _scan_body():
    start = JS.index('  async function scan(qr')
    return JS[start:JS.index('\n  function readQuantity', start)]


def test_scan_takes_a_source_defaulting_to_the_real_scanner():
    assert "async function scan(qr, {source = 'scanner'} = {}) {" in JS


def test_simulator_buttons_and_hooks_scan_as_demo():
    assert "getElementById('demo-scan-employee').addEventListener('click', () => scan(employeeQr(), {source:'demo'}));" in JS
    assert "getElementById('demo-scan-operation').addEventListener('click', () => scan(operationQr(), {source:'demo'}));" in JS
    assert "scanEmployee: () => scan(employeeQr(), {source:'demo'})," in JS
    assert "scanOperation: () => scan(operationQr(), {source:'demo'})," in JS
    # The raw-payload hook stands in for a scanner gun: it must stay 'scanner'.
    assert "scan: qr => scan(String(qr || ''))," in JS
    # Camera scans are real scans too.
    assert 'if (payload) scan(payload);' in JS


def test_demo_scan_on_a_terminal_screen_keeps_the_identified_employee():
    body = _scan_body()
    guard = ("if (source === 'demo' && (flow === 'started' || flow === 'finished' || flow === 'error')) {\n"
             "        if (result.type === 'operation' && employee) flow = 'operation';\n"
             "        else { reset(); flow = 'ready'; }\n"
             "      }")
    assert guard in body
    # The decision uses the result already fetched: exactly one /scan per scan.
    assert body.count('/scan`') == 1
    assert body.index('let flow = state;') > body.index('const result = await api(')
    assert body.index(guard) < body.index("if (flow === 'ready') {")


def test_branches_dispatch_on_flow_not_the_raw_screen_state():
    body = _scan_body()
    assert "if (flow === 'ready') {" in body
    assert "} else if (flow === 'operation' || flow === 'sessions' || quantityStates.includes(flow)) {" in body
    assert "} else if (flow === 'started' || flow === 'finished' || flow === 'error') {" in body
    # `state` is read exactly once, to seed `flow`; the handlers never branch
    # on a state that reset() may have changed underneath them.
    assert body.count("state === ") == 0


def test_real_scanner_terminal_path_is_unchanged():
    body = _scan_body()
    assert "reset(); setTimeout(() => scan(qr), 50);" in body
    # SCN-003 still guards an Operation scan with nobody identified.
    assert "e.code='SCN-003'" in body
