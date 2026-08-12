from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_frontend_modules_are_split_and_loaded():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    html=(ROOT/'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    assert 'async function renderQrPrintCenter' not in app
    assert 'async function renderSessionExceptions' not in app
    for path in ('core/api.js','pages/qr-print.js','pages/session-exceptions.js'):
        assert f'/static/{path}' in html
        assert (ROOT/'app/mesflow/web/static'/path).exists()

def test_playwright_suite_is_packaged():
    for path in ('package.json','playwright.config.js','Dockerfile.playwright','tests/e2e/mesflow.spec.js'):
        assert (ROOT/path).exists()
    compose=(ROOT/'compose.test.yml').read_text(encoding='utf-8')
    assert 'playwright:' in compose
