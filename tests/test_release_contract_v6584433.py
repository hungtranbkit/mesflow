from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_agent_web_release_version_contract():
    assert (ROOT/"VERSION.txt").read_text(encoding="utf-8").strip()==EXPECTED
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==EXPECTED
    release=json.loads((ROOT/"release.json").read_text(encoding="utf-8"))
    assert release.get("version")==EXPECTED
    compose=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert f"mesflow-app:{EXPECTED}" in compose

def test_package_has_required_agent_web_files():
    for rel in ["VERSION.txt","release.json","compose.yml","Dockerfile","app"]:
        assert (ROOT/rel).exists(), rel

def test_previous_version_not_left_in_active_release_metadata():
    active=[
        ROOT/"VERSION.txt",
        ROOT/"release.json",
        ROOT/"compose.yml",
        ROOT/"app"/"mesflow"/"__init__.py",
    ]
    for p in active:
        text=p.read_text(encoding="utf-8")
        assert "65.8.44.32" not in text
