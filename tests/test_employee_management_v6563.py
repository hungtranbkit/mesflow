from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_employee_profile_migration_and_repository():
    migration=(ROOT/'app/migrations/versions/0006_employee_profile.py').read_text(encoding='utf-8')
    repo=(ROOT/'app/mesflow/db/repositories/master_data.py').read_text(encoding='utf-8')
    for field in ('team','birth_date','identity_number','current_address','contract_1','contract_2'):
        assert field in migration
        assert field in repo
    assert 'list_with_stats' in repo
    assert 'WF|EMP|' in repo

def test_employee_ui_is_dedicated():
    js=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    css=(ROOT/'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')
    assert "if(id==='employees')return renderEmployees()" in js
    for text in ('+ Thêm nhân viên','Tổ / Nhóm','CCCD','Tổng SP đạt','employeeModal'):
        assert text in js
    assert '.employee-form' in css
