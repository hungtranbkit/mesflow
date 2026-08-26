from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()
def test_version_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()
