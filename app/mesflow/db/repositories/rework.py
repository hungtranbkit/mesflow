"""Transactional V1 rework queue.

The source Session remains the bucket owner.  Resolving a queue item moves
quantity out of its pending bucket exactly once: repaired pieces increase the
original operation's GOOD result, while scrapped pieces enter SCRAP.  The
ledger is an audit/history record, never a second quantity source.
"""
from __future__ import annotations

from mesflow.db.connection import transaction, fetch_all
from mesflow.db.repositories.base import ConflictError, NotFoundError
from mesflow.db.repositories.production_state import (reconcile_operation_and_po,
    lock_production_order_first_for_session)
from mesflow.domain.audit import record_audit
from mesflow.domain.trace import record_event, record_quantities
from psycopg.types.json import Jsonb
from datetime import date, datetime, time


def _json_safe(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _rework_operation(cur, production_order_id: int, part_id: int):
    cur.execute("SELECT id FROM production_orders WHERE id=%s FOR UPDATE", (production_order_id,))
    if not cur.fetchone():
        raise NotFoundError("production order not found")
    cur.execute("""SELECT o.* FROM operations o
        WHERE o.production_order_id=%s AND o.part_id=%s AND o.is_rework_op=TRUE
        ORDER BY o.id LIMIT 1 FOR UPDATE""", (production_order_id, part_id))
    row = cur.fetchone()
    if row:
        return row
    cur.execute("SELECT code FROM parts WHERE id=%s AND production_order_id=%s", (part_id, production_order_id))
    part = cur.fetchone()
    if not part:
        raise NotFoundError("part not found")
    code = f"REWORK-{production_order_id}-{part['code']}"
    cur.execute("""INSERT INTO operations(
        production_order_id,part_id,code,name,done_qty,defect_qty,rework_qty,
        scrap_qty,status,sort_order,qr,operation_type)
        VALUES(%s,%s,%s,%s,0,0,0,0,'PLANNED',2147483647,%s,'REWORK')
        RETURNING *""", (production_order_id, part_id, code, "SỬA HÀNG", f"WF|OP|{code}"))
    return cur.fetchone()


class ReworkQueueRepository:
    def queue(self, limit: int = 1000):
        rows = fetch_all("""SELECT ws.id source_session_id, ws.operation_id source_operation_id,
            ws.defect_qty,ws.rework_qty,ws.scrap_qty,
            (ws.defect_qty-ws.rework_qty-ws.scrap_qty) pending_qty,
            ws.ended_at source_finished_at,e.id employee_id,e.employee_no,e.name employee_name,
            o.code operation_code,o.name operation_name,po.id production_order_id,po.code po_code,
            p.id part_id,p.code part_code,p.name part_name
          FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id
          JOIN operations o ON o.id=ws.operation_id AND COALESCE(o.operation_type,'PRODUCTION')='PRODUCTION'
          JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
          WHERE ws.status='CLOSED' AND COALESCE(ws.excluded_from_reports,FALSE)=FALSE
            AND ws.defect_qty > ws.rework_qty + ws.scrap_qty
          ORDER BY p.code,ws.ended_at,ws.id LIMIT %s""", (min(max(int(limit), 1), 5000),))
        return rows

    def resolve(self, source_session_id: int, data: dict, *, actor_user_id=None,
                actor_username='', correlation_id=''):
        repaired = max(int(data.get('repaired_qty', data.get('qty_reworked', 0)) or 0), 0)
        scrapped = max(int(data.get('scrapped_qty', data.get('qty_scrapped', 0)) or 0), 0)
        if repaired + scrapped <= 0:
            raise ValueError('Phải nhập số lượng sửa được hoặc loại')
        request_id = str(data.get('request_id') or '').strip()
        if not request_id:
            raise ValueError('request_id required')
        employee_id = int(data.get('employee_id') or 0)
        if employee_id <= 0:
            raise ValueError('employee_id required')
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,2))', (f'rework-{source_session_id}',))
                # PO trước tiên, như mọi đường ghi khác. Advisory lock ở trên
                # chỉ tuần tự hoá rework-với-rework; nó không nói gì với
                # finish()/adjust(), vốn khoá theo thứ tự PO -> session. Câu
                # SELECT bên dưới dùng FOR UPDATE trên một join, nên nó khoá
                # cả ba bảng và production_orders là bảng CUỐI -- ngược chiều.
                # Hai quản đốc, một người resolve hàng chờ sửa và một người sửa
                # số liệu cùng session, là đủ để deadlock.
                lock_production_order_first_for_session(cur, source_session_id)
                cur.execute("""SELECT ws.*,o.production_order_id,o.part_id,o.code operation_code,
                    o.operation_type,po.code po_code
                  FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
                  JOIN production_orders po ON po.id=o.production_order_id
                  WHERE ws.id=%s FOR UPDATE OF ws""", (source_session_id,))
                source = cur.fetchone()
                if not source:
                    raise NotFoundError('source session not found')
                if source['status'] != 'CLOSED' or source.get('operation_type') != 'PRODUCTION':
                    raise ConflictError('Session nguồn không hợp lệ cho hàng chờ sửa')
                # "Còn chờ sửa" phải là số THẤP HƠN giữa hai nguồn: dòng
                # session (tổng cộng dồn, có thể bị lệnh sửa số liệu ghi đè) và
                # rework_ledger (bản ghi bất biến từng lần resolve). Trước đây
                # chỉ đọc dòng session, nên một lệnh chỉnh số liệu đưa
                # rework_qty về 0 sẽ làm chính những sản phẩm đã sửa quay lại
                # hàng chờ -- resolve lần hai thì good_qty đếm hai lần cùng một
                # sản phẩm vật lý, và Operation có thể lên COMPLETED bằng hàng
                # không tồn tại. execution.py chặn ở chiều ghi; đây chặn ở
                # chiều đọc, để dù có dữ liệu cũ lệch sẵn cũng không credit lại.
                from mesflow.db.repositories.execution import _rework_ledger_floor
                ledger_reworked, ledger_scrapped = _rework_ledger_floor(cur, source_session_id)
                already_reworked = max(int(source.get('rework_qty') or 0), ledger_reworked)
                already_scrapped = max(int(source.get('scrap_qty') or 0), ledger_scrapped)
                pending = int(source.get('defect_qty') or 0) - already_reworked - already_scrapped
                if repaired + scrapped > pending:
                    raise ConflictError(f'Số lượng xử lý vượt Chờ sửa ({max(pending,0)})')
                cur.execute('SELECT id,active FROM employees WHERE id=%s FOR SHARE', (employee_id,))
                worker = cur.fetchone()
                if not worker or not worker['active']:
                    raise ConflictError('Nhân viên xử lý không hợp lệ')
                # A request id is unique across kiosk actions; making a
                # resolution replay-safe also prevents double credit on retry.
                cur.execute('SELECT response_json FROM kiosk_idempotency WHERE request_id=%s', (request_id,))
                replay = cur.fetchone()
                if replay:
                    return {**replay['response_json'], 'idempotent_replay': True}
                rework_op = _rework_operation(cur, int(source['production_order_id']), int(source['part_id']))
                # The rework session records the LABOUR (who repaired, when,
                # on which SỬA HÀNG workbench) and deliberately carries NO
                # quantities. This used to write good_qty=repaired /
                # defect_qty=scrapped here as well as crediting the source
                # session below -- two rows describing the same physical
                # pieces. Nothing double-counted only for as long as every
                # single report remembered to filter is_rework_op, and the one
                # query that forgot (po_progress, fixed 2026-09-09) collapsed a
                # whole PO's progress to zero. Zero here restores this module's
                # own stated rule -- "The source Session remains the bucket
                # owner ... never a second quantity source" (see the docstring
                # above and 0044_rework_queue.py) -- and makes the is_rework_op
                # filters defence in depth instead of load-bearing. The
                # quantities live on the source session (running balance) and
                # in rework_ledger (dated audit of this specific action).
                cur.execute("""INSERT INTO work_sessions(
                    employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,
                    good_qty,defect_qty,rework_qty,scrap_qty,start_request_id,finish_request_id,note)
                    VALUES(%s,%s,%s,%s,'CLOSED',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0,0,0,0,%s,%s,%s)
                    RETURNING *""", (employee_id,rework_op['id'],data.get('station_id'),
                    str(data.get('device_uuid') or 'REWORK-QUEUE'),
                    f'{request_id}-START',f'{request_id}-FINISH',str(data.get('note') or '')))
                rework_session = cur.fetchone()
                record_quantities(cur, session=source,
                    good=int(source.get('good_qty') or 0)+repaired,
                    defect=int(source.get('defect_qty') or 0),
                    rework=int(source.get('rework_qty') or 0)+repaired,
                    actor_id=actor_user_id, actor_name=actor_username,
                    source='REWORK_RESOLUTION', reason=str(data.get('note') or ''),
                    correlation_id=correlation_id or request_id)
                cur.execute("""UPDATE work_sessions SET good_qty=good_qty+%s,
                    rework_qty=rework_qty+%s,scrap_qty=scrap_qty+%s,
                    updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *""",
                    (repaired,repaired,scrapped,source_session_id))
                updated = cur.fetchone()
                cur.execute("""INSERT INTO rework_ledger(
                    source_session_id,source_operation_id,rework_session_id,rework_operation_id,
                    employee_id,qty_reworked,qty_scrapped)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (source_session_id,source['operation_id'],rework_session['id'],rework_op['id'],
                     employee_id,repaired,scrapped))
                ledger = cur.fetchone()
                # Rework operation is deliberately excluded from production
                # rollups; source operation is the only credited producer.
                reconcile_operation_and_po(cur, int(source['operation_id']))
                response = _json_safe({'ok': True, 'source_session': dict(updated),
                    'rework_session': dict(rework_session), 'ledger': dict(ledger),
                    'repaired_qty': repaired, 'scrapped_qty': scrapped,
                    'pending_qty': pending-repaired-scrapped, 'idempotent_replay': False})
                cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',
                    (request_id,'REWORK_RESOLVE',Jsonb(response)))
                record_audit(cur, action='REWORK_RESOLVED', entity_type='work_session',
                    entity_id=str(source_session_id), actor_username=actor_username,
                    actor_user_id=actor_user_id, employee_id=employee_id,
                    correlation_id=correlation_id or request_id, before=_json_safe(dict(source)),
                    after=response['source_session'], metadata={'ledger_id': ledger['id'],
                    'repaired_qty': repaired, 'scrapped_qty': scrapped}, source='rework-queue')
                record_event(cur, event_type='REWORK_RESOLVED', category='REWORK',
                    title='Đã xử lý hàng chờ sửa', operation_id=source['operation_id'],
                    session_id=source_session_id, actor_id=actor_user_id,
                    actor_name=actor_username, correlation_id=correlation_id or request_id,
                    metadata={'repaired_qty': repaired, 'scrapped_qty': scrapped,
                              'rework_session_id': rework_session['id']})
                return response
