from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
required=[
 'app/migrations/versions/0002_master_data.py',
 'app/mesflow/db/repositories/master_data.py',
 'app/mesflow/web/master_data.py',
]
for item in required:
    assert (ROOT/item).exists(), item
source='\n'.join(p.read_text(errors='ignore') for p in (ROOT/'app').rglob('*.py'))
assert 'sqlite3' not in source
assert 'PRAGMA' not in source
assert 'INSERT OR IGNORE' not in source
print('phase2 structure tests passed')
