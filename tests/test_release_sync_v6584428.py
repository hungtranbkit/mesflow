from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.28"

def test_release_version_is_exactly_synced():
    assert (ROOT/"VERSION.txt").read_text(encoding="utf-8").strip()==EXPECTED
    init=(ROOT/"app"/"mesflow"/"__init__.py").read_text(encoding="utf-8")
    assert f"__version__='{EXPECTED}'" in init.replace(" ","")
    release=json.loads((ROOT/"release.json").read_text(encoding="utf-8"))
    assert release["version"]==EXPECTED
    compose=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert f"image: mesflow-app:{EXPECTED}" in compose

def test_no_previous_runtime_version_left_in_active_package():
    active=[
        ROOT/"VERSION.txt",
        ROOT/"release.json",
        ROOT/"compose.yml",
        ROOT/"app"/"mesflow"/"__init__.py",
    ]
    for p in active:
        assert "65.8.44.26" not in p.read_text(encoding="utf-8")
        assert "65.8.44.27" not in p.read_text(encoding="utf-8")
