from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def text(path): return (ROOT/path).read_text(encoding='utf-8')

def test_material_flow_trace_contract():
    migration=text('app/migrations/versions/0021_material_flow_trace.py')
    assert 'operation_input_consumption_history' in migration
    assert "origin='BACKFILL'" in migration
    assert 'audit_operation_input_consumption' in migration
    backend=text('app/mesflow/web/master_data.py')
    assert "/operations/<int:operation_id>/material-flow" in backend
    assert 'available_qty' in backend and 'history_count' in backend
    js=text('app/mesflow/web/static/pages/material-flow.js')
    for marker in ('DÒNG VẬT TƯ','Ledger hiện tại','Lịch sử thay đổi','BACKFILL','ADMIN_EDIT'):
        assert marker in js

def test_ledger_mutation_guards():
    repo=text('app/mesflow/db/repositories/master_data.py')
    assert 'Không thể đổi OP nguồn' in repo
    assert 'Không thể giảm sản lượng đạt xuống dưới' in repo  # wording later specified WHICH quantity (đạt/good)
    assert 'Không thể xóa Operation vì đã phát sinh Ledger' in repo
    excel=text('app/mesflow/web/excel_io.py')
    assert 'Không thể Replace cấu trúc Operation' in excel
    assert 'đã có Ledger nên không thể chuyển PO/Part' in excel

def test_material_flow_po_modal_is_real_overlay_and_complete():
    js=text('app/mesflow/web/static/pages/material-flow.js')
    css=text('app/mesflow/web/static/ui.css')
    backend=text('app/mesflow/web/master_data.py')
    assert "className='material-flow-overlay hidden'" in js
    assert 'material-flow-backdrop' in js and 'data-mf-close' in js
    for marker in ('Luồng đầu vào','GOOD còn khả dụng','REWORK còn khả dụng','Operation nhận đầu ra','NHẬN VÀO','CẤP RA'):
        assert marker in js
    assert '.material-flow-overlay{position:fixed;inset:0;z-index:1400' in css
    for marker in ("relation=relation","downstream=[dict(x) for x in downstream]","good_consumed_qty","rework_consumed_qty"):
        assert marker in backend
