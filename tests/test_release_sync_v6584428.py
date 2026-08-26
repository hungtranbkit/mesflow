from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_release_version_is_exactly_synced():
    assert (ROOT/"VERSION.txt").read_text(encoding="utf-8").strip()==EXPECTED
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==EXPECTED
    release=json.loads((ROOT/"release.json").read_text(encoding="utf-8"))
    assert release["version"]==EXPECTED
    compose=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert f"mesflow-app:{EXPECTED}" in compose

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
