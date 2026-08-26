from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()

def test_version():
    assert (R/"VERSION.txt").read_text().strip()==E
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==E  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((R/"release.json").read_text())["version"]==E

def test_kiosk_exports_demo_api():
    s=(R/"app/mesflow/web/static/kiosk.js").read_text()
    assert "window.MESFlowKioskDemo" in s
    assert "open: openDemo" in s
    assert "close: closeDemo" in s
    assert "scanEmployee:" in s
    assert "scanOperation:" in s

def test_normal_button_listener_still_exists():
    s=(R/"app/mesflow/web/static/kiosk.js").read_text()
    assert "demoToggle.addEventListener('click', openDemo)" in s

def test_tutorial_uses_stable_open_helper():
    s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
    assert "async function openKioskDemo(page)" in s
    block=s[s.index("kioskUser: async page=>"):s.index("calendar: async page=>")]
    assert "await openKioskDemo(page);" in block
    assert "await closeKioskDemo(page);" in block
    assert "page.locator('#demo-toggle').click()" not in block

def test_helper_has_dom_fallback():
    s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
    helper=s[s.index("async function openKioskDemo"):s.index("async function login")]
    assert "MESFlowKioskDemo" in helper
    assert "dom-fallback" in helper
    assert "classList.add('open')" in helper
