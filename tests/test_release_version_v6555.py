from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def test_all_runtime_version_sources_are_current():
    version=(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (65,8,33)
    init=(ROOT/'app/mesflow/__init__.py').read_text(encoding='utf-8')
    assert f"__version__ = '{version}'" in init or f"__version__='{version}'" in init
    release=json.loads((ROOT/'release.json').read_text(encoding='utf-8'))
    assert release['version']==version
    assert f'mesflow-app:{version}' in (ROOT/'compose.yml').read_text(encoding='utf-8')
