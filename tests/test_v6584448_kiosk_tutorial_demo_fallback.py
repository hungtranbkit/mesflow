from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
E="65.8.44.48"

def test_version():
    assert (R/"VERSION.txt").read_text().strip()==E
    assert E in (R/"app/mesflow/__init__.py").read_text()
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
    assert "#demo-panel" in block
    assert "toHaveClass(/open/)" in block
    assert "timeout:15000" in block
