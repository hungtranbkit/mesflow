from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_routes_and_ui():
 p=(ROOT/'app/mesflow/web/action_logging.py').read_text();j=(ROOT/'app/mesflow/web/static/pages/system-logs.js').read_text()
 for x in ['/error-traces','/error-traces/stats','/log-retention/runs']: assert x in p
 for x in ['Action Log','Error Trace','Lịch sử retention','Traceback server']: assert x in j  # tab heading is lowercase "retention", not capitalized
def test_version(): assert (ROOT/'VERSION.txt').read_text().strip()  # non-empty, well-formed version string
