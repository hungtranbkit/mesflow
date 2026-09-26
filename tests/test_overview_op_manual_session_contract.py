"""Operation Detail "Bổ sung phiên" (2026-09-26 hotfix) -- static contract.

Behaviour is proven end to end by tests/integration/test_op_detail_manual_session.py
(real PostgreSQL) and tests/e2e/overview-op-manual-session.spec.js (UI). This
file pins the wiring those rely on, so a later edit cannot quietly drop the
permission gate, the idempotency key, the shared formula, or the audit action.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'app/mesflow/web/static/pages/overview.js').read_text(encoding='utf-8')
CSS = (ROOT / 'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')
EX = (ROOT / 'app/mesflow/db/repositories/execution.py').read_text(encoding='utf-8')
ROUTES = (ROOT / 'app/mesflow/web/execution.py').read_text(encoding='utf-8')
AUDIT = (ROOT / 'app/mesflow/domain/audit_presentation.py').read_text(encoding='utf-8')
AN = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')


def _manual_block():
    start = EX.index('    def create_manual_session(')
    return EX[start:EX.index('\n    def ', start + 10)]


def test_actions_are_gated_on_session_edit_and_prefill_employee():
    assert "canManualSession=typeof hasPermission==='function'?hasPermission('session.edit')" in JS
    assert 'data-manual-session-employee="${Number(p.employee_id)}"' in JS
    assert '+ Phiên</button>' in JS
    assert 'data-manual-session-open>+ Bổ sung phiên</button>' in JS
    assert "if(employeeId)select.value=String(employeeId);" in JS
    assert '<span>Bổ sung</span>' in JS


def test_form_has_the_required_fields_and_live_previews():
    for field in ('name="employee_id" required', 'name="started_at" type="datetime-local"',
                  'name="ended_at" type="datetime-local"', 'name="good_qty" type="number" min="0" step="1"',
                  'name="defect_qty" type="number" min="0" step="1"', 'name="reason" type="text" maxlength="500" required',
                  'name="note" type="text"', 'data-manual-duration', 'data-manual-score'):
        assert field in JS, field
    # So định mức reuses the list's own score()/speed(), not a second formula.
    assert "score(standard,{status:'CLOSED',duration_seconds:sec,good_qty:form.good_qty.value,defect_qty:form.defect_qty.value})" in JS
    assert 'modal.dataset.standard=String(standard);' in JS
    # No hardcoded date anywhere in the form defaults.
    form = JS[JS.index('const manualForm='):JS.index('modal.innerHTML=`<div class="op-detail-head"><div><small>Operation Detail · Nhấp đúp')]
    assert not re.search(r'20\d\d-\d\d-\d\d', form)


def test_submit_is_idempotent_and_refreshes_in_place():
    assert "if(form.dataset.saving==='1')return;" in JS
    assert 'form.dataset.requestId=`op-detail-manual-${operationId}-' in JS
    assert "api('/api/supervisor/sessions/manual',{method:'POST'" in JS
    assert 'request_id:form.dataset.requestId' in JS
    assert 'await reloadDetail(created.id);' in JS
    assert "if(!modal.dataset.delegated){modal.dataset.delegated='1';" in JS
    assert "if(highlightId&&!visibleSessions.some(" in JS
    assert '<small class="op-session-flag manual">Bổ sung tay</small>' in JS
    assert 'toast(`Đã bổ sung phiên #' in JS


def test_existing_quantity_edit_is_unchanged():
    assert "canAdjustSessionQty=role==='admin'||role==='super_admin'" in JS
    assert "/api/supervisor/sessions/${sessionId}/adjust" in JS
    assert "await showOperationDetail(operationId);" in JS


def test_route_uses_the_session_edit_boundary():
    route = ROUTES[ROUTES.index("@bp.post('/supervisor/sessions/manual')"):]
    route = route[:route.index('\n@bp.')]
    assert "@roles_required('admin','manager','supervisor')" in route
    assert 'create_manual_session(' in route


def test_repository_creates_a_closed_audited_session_transactionally():
    block = _manual_block()
    assert "'CLOSED'" in block and "'MANUAL_SUPPLEMENT'" in block
    assert 'with transaction() as conn:' in block
    assert "_replay(conn,request_id,'SESSION_MANUAL_CREATE')" in block
    assert 'lock_production_order_for_operation_first(cur,operation_id)' in block
    assert "record_audit(cur,action='SESSION_MANUAL_CREATE'" in block
    assert 'INSERT INTO operation_adjustments' in block and 'VALUES(%s,%s,0,%s,0,%s,0,%s,%s,%s)' in block
    assert 'reconcile_operation_and_po(cur,operation_id)' in block
    assert '_guard_support_operation_quantity(' in block
    assert '_find_employee_session_overlap(cur,employee_id,started_at,ended_at,None,operation_id=operation_id)' in block
    assert "if ended_at<=started_at: raise ValueError" in block
    for key in ("'actor'", "'reason'", "'session_id'", "'operation_id'", "'employee_id'", "'started_at'", "'ended_at'",
                "'good_qty'", "'defect_qty'"):
        assert key in block, key


def test_audit_action_is_catalogued_and_report_exposes_close_reason():
    assert "'SESSION_MANUAL_CREATE': {'label':" in AUDIT
    assert "elif action == 'SESSION_MANUAL_CREATE':" in AUDIT
    assert 'ws.quantity_confirmed,ws.close_reason,' in AN


def test_form_styles_use_radius_tokens():
    block = CSS[CSS.index('/* OP Detail: Bổ sung phiên'):]
    radii = re.findall(r'border-radius:([^;}]+)', block)
    assert radii and all(r.strip().startswith('var(--radius-') for r in radii), radii
    assert '.op-manual-form[hidden]{display:none!important}' in block
    assert '@media(max-width:480px)' in block
