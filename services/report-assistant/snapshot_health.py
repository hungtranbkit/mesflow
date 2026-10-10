"""Container readiness includes both artifacts and the live authorization read."""
import json
import os
from urllib.request import Request, urlopen
from snapshot_store import load

load('/snapshots', 'reports.json', 150)
load('/snapshots', 'active.json', 60)
request = Request('http://mesflow-report-snapshots:8090/scope/1',
                  headers={'Authorization': 'Bearer ' + os.environ['REPORT_SCOPE_KEY']})
with urlopen(request, timeout=3) as response:
    assert response.status == 200 and 'scope' in json.loads(response.read(2048))
