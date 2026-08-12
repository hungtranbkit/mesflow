from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_ui_files():
 assert (ROOT/'app/mesflow/web/templates/login.html').exists()
 assert (ROOT/'app/mesflow/web/templates/app.html').exists()
 assert (ROOT/'app/mesflow/web/static/app.js').exists()
def test_routes():
 text=(ROOT/'app/mesflow/web/app.py').read_text()
 for route in ["@app.get('/')","@app.get('/app')","@app.get('/api/auth/me')"]: assert route in text
