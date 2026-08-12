from pathlib import Path
ROOT=Path('/app/mesflow')
def test_no_sqlite():
    hits=[]
    for p in ROOT.rglob('*.py'):
        s=p.read_text()
        if 'sqlite3' in s or 'workshop.db' in s or 'PRAGMA' in s:
            hits.append(str(p))
    assert not hits,hits
