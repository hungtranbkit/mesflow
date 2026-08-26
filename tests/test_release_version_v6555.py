from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def test_all_runtime_version_sources_are_current():
    version=(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (65,8,33)
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==version
    release=json.loads((ROOT/'release.json').read_text(encoding='utf-8'))
    assert release['version']==version
    assert f'mesflow-app:{version}' in (ROOT/'compose.yml').read_text(encoding='utf-8')
