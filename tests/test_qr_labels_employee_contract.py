from pathlib import Path


def test_employee_qr_query_uses_only_stable_columns():
    source = Path('app/mesflow/web/master_data.py').read_text(encoding='utf-8')
    block = source.split("if kind=='EMPLOYEE':", 1)[1].split("elif kind=='OPERATION':", 1)[0]
    assert 'e.employee_no' in block
    assert 'e.name' in block
    assert 'e.qr' in block
    assert 'e.department' not in block
    assert 'e.position' not in block
    assert "CASE WHEN COALESCE(e.qr,'')=''" in block
