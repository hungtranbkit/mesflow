from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for item in ('app/migrations/versions/0003_execution.py','app/mesflow/db/repositories/execution.py','app/mesflow/web/execution.py'):
    assert (ROOT/item).exists(),item
source='\n'.join(p.read_text(errors='ignore') for p in (ROOT/'app').rglob('*.py'))
for banned in ('sqlite3','PRAGMA','INSERT OR IGNORE','lastrowid'):
    assert banned not in source,banned
print('phase3 structure tests passed')
