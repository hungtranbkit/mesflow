from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_frontend_modules_are_split_and_loaded():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    html=(ROOT/'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    assert 'async function renderQrPrintCenter' not in app
    assert 'async function renderSessionExceptions' not in app
    for path in ('core/api.js','pages/qr-print.js'):
        assert f'/static/{path}' in html
        assert (ROOT/'app/mesflow/web/static'/path).exists()
    # Codex audit E2E finding: pages/session-exceptions.js is confirmed dead
    # code -- app.html deliberately does NOT load it (see that <script>
    # site's own comment): pages/exception-center.js, loaded right after it
    # used to be, unconditionally overwrites the same renderSessionExceptions
    # global. The file itself is kept on disk (not deleted -- a real
    # product decision, not a test fix), so this only checks it still
    # exists and is NOT wired into the page.
    assert '/static/pages/session-exceptions.js' not in html
    assert (ROOT/'app/mesflow/web/static/pages/session-exceptions.js').exists()

def test_playwright_suite_is_packaged():
    for path in ('package.json','playwright.config.js','Dockerfile.playwright','tests/e2e/mesflow.spec.js'):
        assert (ROOT/path).exists()
    compose=(ROOT/'compose.test.yml').read_text(encoding='utf-8')
    assert 'playwright:' in compose
