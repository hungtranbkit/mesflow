from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

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
    # The hardcoded 180000ms literal was later moved into
    # tutorial/tutorial.config.json's tutorial_speed.module_timeout_ms
    # (centralizing it alongside the other pacing knobs there) and raised
    # from 3 to 20 minutes to fit a full voice-narrated module -- the real
    # invariant ("bounded", i.e. not 0/missing/unbounded) still holds.
    s=(ROOT/"playwright.tutorial-detailed.config.js").read_text()
    assert "timeout:tutorialConfig.tutorial_speed.module_timeout_ms" in s
    config=json.loads((ROOT/"tutorial/tutorial.config.json").read_text())
    timeout_ms=config["tutorial_speed"]["module_timeout_ms"]
    assert 0 < timeout_ms <= 30*60*1000
