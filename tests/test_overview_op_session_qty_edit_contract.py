from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/"app/mesflow/web/static/pages/overview.js").read_text()
CSS=(ROOT/"app/mesflow/web/static/ui.css").read_text()
AN=(ROOT/"app/mesflow/db/repositories/analytics.py").read_text()
EX=(ROOT/"app/mesflow/db/repositories/execution.py").read_text()

def test_admin_can_edit_session_quantity_inline_from_op_detail():
    assert "canAdjustSessionQty=role==='admin'||role==='super_admin'" in JS
    assert 'data-edit-session-qty="${s.session_id}"' in JS
    assert 'data-session-qty-form="${s.session_id}"' in JS
    assert "/api/supervisor/sessions/${sessionId}/adjust" in JS
    assert "good_qty:good,defect_qty:defect,rework_qty:rework,reason" in JS

def test_unconfirmed_zero_zero_closed_sessions_are_highlighted():
    assert "Number(s.good_qty||0)===0&&Number(s.defect_qty||0)===0" in JS
    assert "!quantityConfirmed(s.quantity_confirmed)" in JS
    assert "needs-quantity" in JS
    assert "0/0 · Chưa xác nhận sản lượng" in JS
    assert ".op-detail-session-item.needs-quantity" in CSS

def test_adjusted_sessions_surface_audit_state():
    assert "adjustment_count" in AN
    assert "last_adjusted_at" in AN
    assert "last_adjustment_reason" in AN
    assert "Đã điều chỉnh" in JS
    assert ".op-session-flag.adjusted" in CSS

def test_existing_adjust_flow_confirms_quantity_and_writes_audit():
    assert "quantity_confirmed=TRUE" in EX
    assert "INSERT INTO operation_adjustments" in EX
    assert "Điều chỉnh sản lượng phiên làm việc" in EX

def test_edit_requires_reason_and_preserves_rework_constraint():
    assert "if(!reason)return alert('Phải nhập lý do chỉnh sửa để lưu audit.')" in JS
    assert "if(rework>defect)" in JS
    assert "rework>defect" in EX
