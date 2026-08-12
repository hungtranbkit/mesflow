from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.35"

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    assert EXPECTED in (ROOT/"app"/"mesflow"/"__init__.py").read_text()
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"image: mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_note_does_not_use_actionability_scroll():
    s=(ROOT/"tests"/"e2e"/"tutorial-detailed.spec.js").read_text()
    block=s[s.index("async function note"):s.index("async function login")]
    assert "scrollIntoViewIfNeeded" not in block
    assert "target.scrollIntoView" in block
    assert "candidates.find" in block

def test_batch_runner_continues_after_module_failure():
    s=(ROOT/"scripts"/"make-user-guide-video.sh").read_text()
    assert "FAILED=()" in s
    assert "Retrying once with fresh browser" in s
    assert "continuing with remaining videos" in s

def test_timeout_is_bounded():
    s=(ROOT/"playwright.tutorial-detailed.config.js").read_text()
    assert "timeout:180000" in s
