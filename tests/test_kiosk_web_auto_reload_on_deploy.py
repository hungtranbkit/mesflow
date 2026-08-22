"""Web kiosk auto-update on redeploy.

Context: a web kiosk machine can be physically locked (no keyboard/mouse
access) with no remote admin either -- its browser tab, once loaded, ran
whatever JS/CSS/HTML it fetched at that moment forever. Deploying a fix to
the server changed nothing for that already-open tab: kiosk.js had no
version check or reload, so /static/kiosk.css?v={{version}} cache-busting
only takes effect on the NEXT page load, which never came.

Fix: kiosk.html now stamps the loaded version onto <html data-version=...>;
/api/kiosk-web/heartbeat (already polled every 30s) now also returns the
server's current version; kiosk.js compares the two and calls
location.reload() -- but only when idle (state==='ready', demo panel
closed), so an operator mid-task is never interrupted.

Verified live (see commit message) with a real server + Playwright: an
idle tab reloads within one heartbeat cycle when the server reports a
different version; a tab parked mid-flow does not.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_kiosk_page_stamps_its_loaded_version():
    html = (ROOT / 'app/mesflow/web/templates/kiosk.html').read_text(encoding='utf-8')
    assert 'data-version="{{ version }}"' in html


def test_heartbeat_endpoint_returns_current_server_version():
    source = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    fn = source.split('def kiosk_web_heartbeat():', 1)[1].split('\n@bp.', 1)[0]
    assert 'version=__version__' in fn


def test_kiosk_js_reloads_only_when_idle_on_version_mismatch():
    js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    fn_start = 'function reloadIfNewVersionAvailable(serverVersion) {'
    assert fn_start in js
    fn = js.split(fn_start, 1)[1].split('\n  async function sendHeartbeat', 1)[0]
    # Never reload on a no-op/missing comparison.
    assert 'serverVersion === loadedVersion' in fn
    # Never interrupt an operator mid-task or with the demo panel open.
    assert "state !== 'ready'" in fn
    assert 'demoIsOpen()' in fn
    assert 'window.location.reload()' in fn
    # sendHeartbeat must actually read the response and feed it in.
    hb = js.split('async function sendHeartbeat() {', 1)[1]
    assert 'reloadIfNewVersionAvailable(data.version)' in hb
