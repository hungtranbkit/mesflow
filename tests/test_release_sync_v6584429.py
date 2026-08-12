from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.29"
def test_version_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    assert EXPECTED in (ROOT/"app"/"mesflow"/"__init__.py").read_text()
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"image: mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()
