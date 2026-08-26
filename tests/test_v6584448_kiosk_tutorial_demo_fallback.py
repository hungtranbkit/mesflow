from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E=(R/"VERSION.txt").read_text().strip()

def test_version():
    assert (R/"VERSION.txt").read_text().strip()==E
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==E  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((R/"release.json").read_text())["version"]==E

def test_tutorial_demo_fallback_exists():
    s=(R/"app/mesflow/web/static/kiosk.js").read_text()
    assert "ensureTutorialDemoOptions" in s
    assert "showTutorialDemoFallback" in s
    assert "WF|EMP|TUT-E06" in s
    assert "WF|OP|TUT39-CUT" in s

def test_fallback_only_in_tutorial_mode():
    s=(R/"app/mesflow/web/static/kiosk.js").read_text()
    block=s[s.index("function ensureTutorialDemoOptions"):s.index("async function loadDemoData")]
    assert "if (!tutorialMode) return" in block

def test_demo_api_has_tutorial_timeout():
    s=(R/"app/mesflow/web/static/kiosk.js").read_text()
    block=s[s.index("async function loadDemoData"):s.index("function openDemo")]
    assert "Promise.race" in block
    assert "6000" in block
    assert "showTutorialDemoFallback" in block

def test_tutorial_waits_for_open_panel():
    s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
    block=s[s.index("kioskUser: async page=>"):s.index("calendar: async page=>")]
    # The actual wait-for-open-panel logic now lives in the shared
    # openKioskDemo() helper (called 4x from this block) instead of being
    # inlined here -- a DRY refactor, not a removal of the wait.
    assert "openKioskDemo(page)" in block
    helper=s[s.index("async function openKioskDemo"):s.index("async function selectTutorialDemoData")]
    assert "#demo-panel" in helper
    assert "toHaveClass(/open/)" in helper
    assert "timeout:15000" in helper
