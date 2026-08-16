from __future__ import annotations

from .base import ConflictError, NotFoundError
from mesflow.domain.trace import record_event


TERMINAL_OPERATION_STATUSES = {'COMPLETED', 'CANCELLED'}


def lock_idempotency_key(cur, request_id: str) -> None:
    """Serialize retries for one request id before reading/writing its replay row."""
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (request_id,))


def reconcile_operation(cur, operation_id: int):
    """Rebuild one Operation aggregate and state from immutable session facts."""
    cur.execute('''SELECT o.id,o.code,o.status,o.production_order_id,COALESCE(po.planned_quantity,0) planned_quantity
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        WHERE o.id=%s FOR UPDATE OF o,po''', (operation_id,))
    operation = cur.fetchone()
    if not operation:
        raise NotFoundError('operation not found')
    cur.execute('''SELECT COUNT(*) session_count,
          COUNT(*) FILTER (WHERE status='OPEN') open_session_count,
          COALESCE(SUM(good_qty) FILTER (WHERE status='CLOSED'),0) good_qty,
          COALESCE(SUM(defect_qty) FILTER (WHERE status='CLOSED'),0) defect_qty,
          COALESCE(SUM(rework_qty) FILTER (WHERE status='CLOSED'),0) rework_qty
        FROM work_sessions WHERE operation_id=%s''', (operation_id,))
    facts = cur.fetchone() or {}
    current = str(operation.get('status') or 'PLANNED').upper()
    sessions = int(facts.get('session_count') or 0)
    open_sessions = int(facts.get('open_session_count') or 0)
    good = int(facts.get('good_qty') or 0)
    defect = int(facts.get('defect_qty') or 0)
    rework = int(facts.get('rework_qty') or 0)
    planned = int(operation.get('planned_quantity') or 0)
    if current == 'CANCELLED':
        status = 'CANCELLED'
    elif open_sessions:
        status = 'IN_PROGRESS'
    elif current == 'COMPLETED' and sessions == 0:
        status = 'COMPLETED'
    elif planned > 0 and good >= planned:
        status = 'COMPLETED'
    elif sessions:
        status = 'IN_PROGRESS'
    elif current in {'DRAFT', 'PLANNED', 'RELEASED', 'READY', 'PAUSED'}:
        status = current
    else:
        status = 'PLANNED'
    cur.execute('''UPDATE operations SET done_qty=%s,defect_qty=%s,rework_qty=%s,status=%s,
          updated_at=CURRENT_TIMESTAMP WHERE id=%s
          RETURNING id,production_order_id,done_qty,defect_qty,rework_qty,status''',
        (good, defect, rework, status, operation_id))
    result = dict(cur.fetchone())
    if status!=current:
        record_event(cur,event_type='OPERATION_COMPLETED' if status=='COMPLETED' else ('OPERATION_STARTED' if status=='IN_PROGRESS' else 'OPERATION_STATUS_CHANGED'),
          category='OPERATION',title='Operation hoàn tất' if status=='COMPLETED' else ('Operation bắt đầu' if status=='IN_PROGRESS' else 'Trạng thái Operation thay đổi'),
          operation_id=operation_id,source='NATIVE',metadata={'previous_status':current,'status':status})
    result.update(session_count=sessions, open_session_count=open_sessions)
    return result


def reconcile_production_order(cur, po_id: int):
    """Derive PO state from its reconciled Operation states."""
    cur.execute('SELECT id,code,status FROM production_orders WHERE id=%s FOR UPDATE', (po_id,))
    po = cur.fetchone()
    if not po:
        raise NotFoundError('production order not found')
    cur.execute('''SELECT COUNT(*) operation_count,
          COUNT(*) FILTER (WHERE status='COMPLETED') completed_count,
          COUNT(*) FILTER (WHERE status='CANCELLED') cancelled_count,
          COUNT(*) FILTER (WHERE status='IN_PROGRESS') running_count,
          EXISTS(SELECT 1 FROM work_sessions ws JOIN operations x ON x.id=ws.operation_id
                 WHERE x.production_order_id=%s) has_history
        FROM operations WHERE production_order_id=%s''', (po_id, po_id))
    facts = cur.fetchone() or {}
    current = str(po.get('status') or 'DRAFT').upper()
    total = int(facts.get('operation_count') or 0)
    completed = int(facts.get('completed_count') or 0)
    if current == 'CANCELLED':
        status = 'CANCELLED'
    elif total and completed == total:
        status = 'COMPLETED'
    elif int(facts.get('running_count') or 0) or bool(facts.get('has_history')) or current in {'IN_PROGRESS', 'COMPLETED'}:
        status = 'IN_PROGRESS'
    else:
        status = current
    cur.execute('UPDATE production_orders SET status=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING id,code,status',
                (status, po_id))
    result = dict(cur.fetchone())
    if status!=current:
        record_event(cur,event_type='PO_COMPLETED' if status=='COMPLETED' else 'PO_STATUS_CHANGED',category='PO',
          title='Production Order hoàn tất' if status=='COMPLETED' else 'Trạng thái Production Order thay đổi',po_id=po_id,source='NATIVE',metadata={'previous_status':current,'status':status})
    result.update(operation_count=total, completed_count=int(facts.get('completed_count') or 0),
                  cancelled_count=int(facts.get('cancelled_count') or 0))
    return result


def reconcile_operation_and_po(cur, operation_id: int):
    operation = reconcile_operation(cur, operation_id)
    po = reconcile_production_order(cur, int(operation['production_order_id']))
    return {'operation': operation, 'production_order': po}


def reconcile_po_tree(cur, po_id: int):
    cur.execute('SELECT id FROM production_orders WHERE id=%s FOR UPDATE', (po_id,))
    if not cur.fetchone():
        raise NotFoundError('production order not found')
    cur.execute('SELECT id FROM operations WHERE production_order_id=%s ORDER BY id FOR UPDATE', (po_id,))
    operation_ids = [int(row['id']) for row in cur.fetchall()]
    operations = [reconcile_operation(cur, operation_id) for operation_id in operation_ids]
    return {'operations': operations, 'production_order': reconcile_production_order(cur, po_id)}


def lock_startable_operation(cur, operation_id: int):
    """Reconcile stale state, lock the graph, then enforce the single Start guard."""
    reconciled = reconcile_operation_and_po(cur, operation_id)
    cur.execute('''SELECT o.id,o.code,o.name,o.status,o.production_order_id,o.predecessor_operation_id,
               o.input_flow_enabled,o.input_source_operation_id,po.status po_status,po.code po_code
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        WHERE o.id=%s FOR UPDATE OF o,po''', (operation_id,))
    operation = cur.fetchone()
    status = str(operation.get('status') or '').upper()
    if status in TERMINAL_OPERATION_STATUSES:
        raise ConflictError(f"Operation {operation.get('code') or operation_id} đang ở trạng thái {status}, không thể Start session")
    if str(operation.get('po_status') or '').upper() != 'IN_PROGRESS':
        raise ConflictError(f"PO {operation.get('po_code') or ''} chưa Start hoặc đang tạm dừng")
    operation['reconciled'] = reconciled
    return operation
