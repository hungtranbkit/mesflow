from pathlib import Path
SRC=(Path(__file__).resolve().parents[1]/'app/mesflow/web/app.py').read_text()
TPL=(Path(__file__).resolve().parents[1]/'app/mesflow/web/templates/app.html').read_text()

def test_static_assets_force_revalidation():
    assert "request.path.startswith('/static/')" in SRC
    assert "response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'" in SRC
    assert "response.headers['Pragma'] = 'no-cache'" in SRC
    assert "response.headers['Expires'] = '0'" in SRC

def test_main_assets_are_versioned():
    assert '/static/ui.css?v={{ version }}' in TPL
    assert '/static/app.js?v={{ version }}' in TPL
    assert '/static/pages/overview.js?v={{ version }}' in TPL
