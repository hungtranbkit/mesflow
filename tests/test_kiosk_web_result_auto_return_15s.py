"""Web kiosk: the result screen returns itself to "chờ quét thẻ nhân viên".

Context: a shop-floor kiosk stands alone between two workers. kiosk.js did
arm a reset after a successful finish -- but through scheduleReset(), which
bailed out entirely (`if (demoIsOpen()) return;`) whenever the simulation
panel was open. That panel is how a browser operator drives this kiosk (a
laptop has no scanner gun), and openDemo() additionally cleared any pending
timer, so the "ĐÃ GHI NHẬN" screen stayed up forever: the next worker walked
up to someone else's result and a kiosk that looked dead.

Fix: a successful finish arms the return unconditionally (force) at
FINISHED_RESET_MS = 15s; show() cancels any pending return on every
transition, so a new flow started inside the window can never be wiped by
the previous screen's timer; a failed submit still arms nothing, keeping
un-submitted quantities on screen for THỬ LẠI.

Behavioral proof (fake clock, all four branches):
tests/e2e/kiosk-result-auto-return.spec.js.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')


def _function_body(name, end_marker):
    start = JS.index(name)
    return JS[start:JS.index(end_marker, start)]


def test_result_screen_returns_to_waiting_after_fifteen_seconds():
    assert 'const FINISHED_RESET_MS = 15000;' in JS
    finish = _function_body('  async function finish() {', '\n  input.addEventListener')
    # The timer is armed only after the await resolved, i.e. on a real
    # backend success -- never optimistically before the request.
    success = finish.split("show('finished')", 1)[0]
    assert 'await api(' in success
    assert "show('finished'); scheduleReset(FINISHED_RESET_MS, {force:true});" in finish


def test_auto_return_is_not_suppressed_by_the_simulation_panel():
    schedule = _function_body('  function scheduleReset(', '\n  const ERROR_HELP')
    # Still respects the panel for ordinary screens, but a forced arm wins.
    assert 'if (demoIsOpen() && !force) return;' in schedule
    open_demo = _function_body('  function openDemo() {', '\n  function closeDemo')
    assert 'clearTimeout(resetTimer)' not in open_demo
    assert "if (state !== 'finished') cancelReset();" in open_demo


def test_every_transition_cancels_a_pending_auto_return():
    show = _function_body('  function show(name) {', '\n  function focusScanner')
    assert 'cancelReset();' in show
    assert show.index('cancelReset();') < show.index('screens.forEach')
    reset = _function_body('  function reset() {', "\n    show('ready');")
    assert 'cancelReset();' in reset


def test_failed_submit_neither_clears_nor_arms_anything():
    finish = _function_body('  async function finish() {', '\n  input.addEventListener')
    failure = finish.split('} catch (error) {', 1)[1]
    assert 'scheduleReset' not in failure
    assert 'reset()' not in failure
    # The un-submitted quantities stay on screen behind a retry button.
    assert "document.getElementById('finish-submit-retry').hidden = false;" in failure
    assert "show('finish-confirm');" in failure
