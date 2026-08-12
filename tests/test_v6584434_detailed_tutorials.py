from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.34"

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    assert EXPECTED in (ROOT/"app"/"mesflow"/"__init__.py").read_text()
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"image: mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_detailed_video_modules_present():
    spec=(ROOT/"tests"/"e2e"/"tutorial-detailed.spec.js").read_text()
    for name in ["overview","dashboard","po","templates","material","sessions","exceptions","employees","kioskAdmin","kioskUser","calendar","users","logs"]:
        assert f"  {name}:" in spec

def test_linux_runner_uses_writable_home_workspace():
    sh=(ROOT/"scripts"/"make-user-guide-video.sh").read_text()
    assert '$HOME/.mesflow-video' in sh
    assert '$HOME/mesflow-user-guide' in sh
    assert "13_system_logs" not in sh
    assert "12_system_logs:logs" in sh

def test_kiosk_video_is_non_mutating():
    spec=(ROOT/"tests"/"e2e"/"tutorial-detailed.spec.js").read_text()
    kiosk=spec[spec.index("kioskUser:"):spec.index("calendar:")]
    assert "page.goto('/kiosk')" in kiosk
    assert "page.request.post" not in kiosk
    assert "KHÔNG gửi dữ liệu sản xuất thật" in kiosk
