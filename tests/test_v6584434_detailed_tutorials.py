from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_detailed_video_modules_present():
    spec=(ROOT/"tests"/"e2e"/"tutorial-detailed.spec.js").read_text()
    for name in ["overview","dashboard","po","templates","material","sessions","exceptions","employees","kioskAdmin","kioskUser","employeeProductivity","calendar","users","logs"]:
        assert f"  {name}:" in spec

def test_linux_runner_uses_writable_home_workspace():
    sh=(ROOT/"scripts"/"make-user-guide-video.sh").read_text()
    assert '$HOME/.mesflow-video' in sh
    assert '$HOME/mesflow-user-guide' in sh
    # 2026-09-03: 10_employee_productivity inserted after kioskUser, shifting
    # calendar/users/logs/commonCases up by one slot (10-13 -> 11-14).
    assert "14_system_logs" not in sh
    assert "13_system_logs:logs" in sh
    assert "10_employee_productivity:employeeProductivity" in sh

def test_kiosk_video_only_touches_dedicated_tutorial_fixtures():
    """Was test_kiosk_video_is_non_mutating: originally asserted the kiosk
    video never called any API directly (`page.request.post` at all) and
    never left tutorial=1 out of the URL. The recording has since been
    deliberately redesigned to drive the REAL kiosk UI end-to-end (a more
    realistic video) instead of a purely simulated walkthrough -- it now
    starts/finishes an actual work session through genuine UI clicks, and
    proactively cleans up ('pre') any leftover open session from a
    previous recording run via one page.request.post call before the
    on-camera part even starts. The safety invariant that survived this
    redesign, and that still matters, is scope: every mutation is against
    the dedicated TUT-E06/TUT39-CUT tutorial fixtures only (never a real
    employee/operation), selected via the shared selectTutorialDemoData()
    helper, and the on-camera walkthrough itself never calls the API
    directly -- it only ever clicks through the real UI."""
    spec=(ROOT/"tests"/"e2e"/"tutorial-detailed.spec.js").read_text()
    kiosk=spec[spec.index("kioskUser:"):spec.index("calendar:")]
    assert "page.goto('/kiosk?tutorial=1')" in kiosk
    # Only the pre-flight cleanup (before recording starts) may call the API
    # directly; everything from that goto() onward must be pure UI clicks.
    on_camera=kiosk[kiosk.index("page.goto('/kiosk?tutorial=1')"):]
    assert "page.request.post" not in on_camera
    assert "selectTutorialDemoData(page)" in kiosk
    helper=spec[spec.index("async function selectTutorialDemoData"):spec.index("async function selectTutorialDemoData")+600]
    assert "TUT-E06" in helper and "TUT39-CUT" in helper
