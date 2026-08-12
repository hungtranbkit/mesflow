from __future__ import annotations
import hashlib,secrets
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from psycopg.types.json import Jsonb
from typing import Any
from mesflow.db.connection import transaction,fetch_all,fetch_one
from .base import NotFoundError,ConflictError,RepositoryError
from .production_state import lock_idempotency_key,lock_startable_operation,reconcile_operation_and_po
from .scheduling import dispatch_state_from_db


def _json_safe(value: Any):
    """Convert database values to objects safe for JSON/JSONB serialization."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value




def _find_employee_session_overlap(cur, employee_id:int, started_at, ended_at=None, exclude_session_id:int|None=None):
    """Return one conflicting session using PostgreSQL half-open time ranges [start, end)."""
    params=[employee_id]
    exclude_sql=''
    if exclude_session_id is not None:
        exclude_sql=' AND ws.id<>%s'
        params.append(exclude_session_id)
    params.extend([started_at,ended_at])
    cur.execute(f"""SELECT ws.id,ws.status,ws.started_at,ws.ended_at,o.code operation_code,o.name operation_name
        FROM work_sessions ws LEFT JOIN operations o ON o.id=ws.operation_id
        WHERE ws.employee_id=%s {exclude_sql}
          AND tstzrange(ws.started_at,COALESCE(ws.ended_at,'infinity'::timestamptz),'[)')
              && tstzrange(%s::timestamptz,COALESCE(%s::timestamptz,'infinity'::timestamptz),'[)')
        ORDER BY ws.started_at LIMIT 1""",params)
    return cur.fetchone()

def _raise_overlap(conflict):
    if conflict:
        label=conflict.get('operation_code') or conflict.get('operation_name') or conflict.get('id')
        raise ConflictError(f"Thời gian session bị chồng với Session #{conflict['id']} ({label}). Hãy điều chỉnh giờ bắt đầu/kết thúc.")



def _operation_flow(cur, operation_id:int):
    cur.execute("""SELECT o.id,o.code,o.production_order_id,o.input_flow_enabled,o.input_source_operation_id,
                          o.input_source_kind,o.defects_consume_input,COALESCE(o.done_qty,0) done_qty,
                          COALESCE(o.defect_qty,0) defect_qty,COALESCE(o.rework_qty,0) rework_qty
                   FROM operations o WHERE o.id=%s FOR UPDATE""",(operation_id,))
    return cur.fetchone()

def _validate_and_upsert_input_consumption(cur, *, session_id:int, target_operation_id:int, good_qty:int, defect_qty:int, origin:str='RUNTIME'):
    """Validate shared upstream stock and upsert the session ledger row atomically."""
    target=_operation_flow(cur,target_operation_id)
    if not target:
        raise NotFoundError('operation not found')
    source_id=target.get('input_source_operation_id') if target.get('input_flow_enabled') else None
    if not source_id:
        cur.execute('DELETE FROM operation_input_consumptions WHERE session_id=%s',(session_id,))
        return None
    cur.execute("SELECT id,code,production_order_id,COALESCE(done_qty,0) done_qty,COALESCE(rework_qty,0) rework_qty FROM operations WHERE id=%s FOR UPDATE",(source_id,))
    source=cur.fetchone()
    if not source or source['production_order_id']!=target['production_order_id']:
        raise ConflictError('OP nguồn đầu vào không hợp lệ')
    consume_good=max(int(good_qty or 0),0)
    consume_defect=max(int(defect_qty or 0),0) if target.get('defects_consume_input') else 0
    requested=consume_good+consume_defect
    source_kind=str(target.get('input_source_kind') or 'GOOD').upper()
    if source_kind not in ('GOOD','REWORK'):
        source_kind='GOOD'
    cur.execute("""SELECT COALESCE(SUM(good_qty_consumed+defect_qty_consumed),0) consumed
                   FROM operation_input_consumptions
                   WHERE source_operation_id=%s AND source_qty_kind=%s AND session_id<>%s""",(source_id,source_kind,session_id))
    consumed=int((cur.fetchone() or {}).get('consumed') or 0)
    supplied=int(source.get('rework_qty') or 0) if source_kind=='REWORK' else int(source.get('done_qty') or 0)
    available=max(supplied-consumed,0)
    if requested>available:
        if supplied<=0:
            label='lỗi sửa được' if source_kind=='REWORK' else 'sản lượng đạt'
            raise ConflictError(
                f"OP nguồn {source.get('code') or source_id} chưa có {label} để cấp. "
                "Hãy kết thúc ít nhất một session OP nguồn và nhập số lượng trước."
            )
        label='rework' if source_kind=='REWORK' else 'đạt'
        raise ConflictError(
            f"Đầu vào {label} khả dụng chỉ còn {available} sản phẩm từ OP nguồn {source.get('code') or source_id}. "
            f"Tổng đã phân bổ cho các OP đích khác: {consumed}."
        )
    cur.execute("""INSERT INTO operation_input_consumptions(
                       source_operation_id,target_operation_id,session_id,good_qty_consumed,defect_qty_consumed,source_qty_kind,origin,updated_at
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                   ON CONFLICT(session_id) DO UPDATE SET
                       source_operation_id=EXCLUDED.source_operation_id,
                       target_operation_id=EXCLUDED.target_operation_id,
                       good_qty_consumed=EXCLUDED.good_qty_consumed,
                       defect_qty_consumed=EXCLUDED.defect_qty_consumed,
                       source_qty_kind=EXCLUDED.source_qty_kind,
                       origin=EXCLUDED.origin,updated_at=CURRENT_TIMESTAMP
                   RETURNING *""",(source_id,target_operation_id,session_id,consume_good,consume_defect,source_kind,origin))
    return cur.fetchone()

class KioskRepository:
    def register(self,data:dict[str,Any]):
        device_uuid=str(data.get('device_uuid','')).strip()
        if not device_uuid: raise ValueError('device_uuid required')
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,firmware_version,last_ip,last_seen_at)
                VALUES(%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT(device_uuid) DO UPDATE SET device_name=EXCLUDED.device_name,
                firmware_version=EXCLUDED.firmware_version,last_ip=EXCLUDED.last_ip,last_seen_at=CURRENT_TIMESTAMP
                RETURNING *""",(device_uuid,str(data.get('device_name','')),str(data.get('firmware_version','')),str(data.get('last_ip',''))))
                return cur.fetchone()
    def approve(self,identity_id:int,station_id:int):
        token=secrets.token_urlsafe(32); token_hash=hashlib.sha256(token.encode()).hexdigest()
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE kiosk_identities SET station_id=%s,status='ACTIVE',token_hash=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(station_id,token_hash,identity_id))
                row=cur.fetchone()
                if not row: raise NotFoundError('kiosk identity not found')
                return row,token
    def verify_token(self,device_uuid:str,token:str):
        row=fetch_one("SELECT * FROM kiosk_identities WHERE device_uuid=%s AND status='ACTIVE'",(device_uuid,))
        if not row or hashlib.sha256(token.encode()).hexdigest()!=row['token_hash']:
            raise RepositoryError('invalid kiosk token')
        return row
    def verify_token_any(self,token:str):
        token=str(token or '').strip()
        if not token:
            raise RepositoryError('missing kiosk token')
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        row=fetch_one("SELECT * FROM kiosk_identities WHERE token_hash=%s AND status='ACTIVE' ORDER BY updated_at DESC,id DESC LIMIT 1",(token_hash,))
        if not row:
            raise RepositoryError('invalid kiosk token')
        return row
    def heartbeat(self,device_uuid:str,data:dict[str,Any]):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT station_id FROM kiosk_identities WHERE device_uuid=%s AND status='ACTIVE'",(device_uuid,))
                identity=cur.fetchone()
                if not identity: raise NotFoundError('active kiosk identity not found')
                cur.execute("""INSERT INTO kiosk_status(device_uuid,station_id,ui_state,health_state,queue_size,wifi_rssi,free_heap,last_error,last_heartbeat_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                ON CONFLICT(device_uuid) DO UPDATE SET station_id=EXCLUDED.station_id,ui_state=EXCLUDED.ui_state,
                health_state=EXCLUDED.health_state,queue_size=EXCLUDED.queue_size,wifi_rssi=EXCLUDED.wifi_rssi,
                free_heap=EXCLUDED.free_heap,last_error=EXCLUDED.last_error,last_heartbeat_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                RETURNING *""",(device_uuid,identity['station_id'],str(data.get('ui_state','UNKNOWN')),str(data.get('health_state','OK')),int(data.get('queue_size',0) or 0),data.get('wifi_rssi'),data.get('free_heap'),str(data.get('last_error',''))))
                return cur.fetchone()

    def heartbeat_web_demo(self,device_uuid:str,data:dict[str,Any]):
        """Heartbeat for the browser demo kiosk.

        Only WEB-* identities are accepted. This keeps the demo path separate
        from hardware kiosks, which still require an approved token.
        """
        device_uuid=str(device_uuid or '').strip()
        if not device_uuid.upper().startswith('WEB-'):
            raise ValueError('web kiosk device_uuid must start with WEB-')
        device_name=str(data.get('device_name') or 'Web Kiosk Demo').strip()[:120]
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,firmware_version,last_ip,last_seen_at,status,updated_at)
                    VALUES(%s,%s,%s,%s,CURRENT_TIMESTAMP,'ACTIVE',CURRENT_TIMESTAMP)
                    ON CONFLICT(device_uuid) DO UPDATE SET device_name=EXCLUDED.device_name,
                    firmware_version=EXCLUDED.firmware_version,last_ip=EXCLUDED.last_ip,last_seen_at=CURRENT_TIMESTAMP,
                    status='ACTIVE',updated_at=CURRENT_TIMESTAMP
                    RETURNING station_id""",
                    (device_uuid,device_name,str(data.get('firmware_version') or 'WEB-DEMO'),str(data.get('last_ip') or '')))
                identity=cur.fetchone() or {}
                cur.execute("""INSERT INTO kiosk_status(device_uuid,station_id,ui_state,health_state,queue_size,wifi_rssi,free_heap,last_error,last_heartbeat_at,updated_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                    ON CONFLICT(device_uuid) DO UPDATE SET station_id=EXCLUDED.station_id,ui_state=EXCLUDED.ui_state,
                    health_state=EXCLUDED.health_state,queue_size=EXCLUDED.queue_size,wifi_rssi=EXCLUDED.wifi_rssi,
                    free_heap=EXCLUDED.free_heap,last_error=EXCLUDED.last_error,last_heartbeat_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                    RETURNING *""",
                    (device_uuid,identity.get('station_id'),str(data.get('ui_state') or 'READY'),
                     str(data.get('health_state') or 'OK'),int(data.get('queue_size',0) or 0),
                     data.get('wifi_rssi'),data.get('free_heap'),str(data.get('last_error') or '')))
                return cur.fetchone()

    def management_overview(self):
        summary=fetch_one("""SELECT
          COUNT(*) identity_count,
          COUNT(*) FILTER (WHERE ki.status='PENDING') pending_count,
          COUNT(*) FILTER (WHERE ki.status='ACTIVE') active_count,
          COUNT(*) FILTER (WHERE ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes') online_count,
          COUNT(*) FILTER (WHERE ks.last_error<>'' OR ks.health_state IN ('ERROR','DEGRADED')) error_count,
          (SELECT COUNT(*) FROM kiosk_client_events WHERE status='rejected') offline_conflict_count
        FROM kiosk_identities ki LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid""") or {}
        kiosks=fetch_all("""SELECT ki.id,ki.device_uuid,ki.device_name,ki.station_id,ki.status,ki.firmware_version,ki.last_ip,ki.last_seen_at,ki.created_at,
          s.code station_code,s.name station_name,s.workshop,s.production_line,
          ks.ui_state,ks.health_state,ks.queue_size,ks.wifi_rssi,ks.free_heap,ks.last_error,ks.last_heartbeat_at,
          CASE WHEN ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes' THEN TRUE ELSE FALSE END online,
          (SELECT COUNT(*) FROM kiosk_events ke WHERE ke.device_uuid=ki.device_uuid AND ke.status='OPEN' AND ke.severity IN ('ERROR','CRITICAL')) open_error_count,
          (SELECT MAX(ke.occurred_at) FROM kiosk_events ke WHERE ke.device_uuid=ki.device_uuid) last_event_at,
          (SELECT COUNT(*) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid AND ce.status='accepted') offline_synced_count,
          (SELECT COUNT(*) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid AND ce.status='rejected') offline_conflict_count,
          (SELECT MAX(ce.processed_at) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid) last_offline_sync_at
        FROM kiosk_identities ki LEFT JOIN stations s ON s.id=ki.station_id LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
        ORDER BY online DESC,open_error_count DESC,ki.status,ki.device_name,ki.device_uuid""")
        return {'summary':dict(summary),'kiosks':[dict(x) for x in kiosks]}

    def bind_legacy(self,data:dict[str,Any],last_ip:str=''):
        device_uuid=str(data.get('device_uuid') or data.get('device_id') or '').strip()
        station_code=str(data.get('station_code') or '').strip()
        if not device_uuid: raise ValueError('device_id required')
        with transaction() as conn:
            with conn.cursor() as cur:
                station_id=None
                if station_code:
                    cur.execute('SELECT id FROM stations WHERE upper(code)=upper(%s) LIMIT 1',(station_code,)); st=cur.fetchone(); station_id=st['id'] if st else None
                token=secrets.token_urlsafe(32); token_hash=hashlib.sha256(token.encode()).hexdigest()
                cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,station_id,status,token_hash,firmware_version,last_ip,last_seen_at)
                  VALUES(%s,%s,%s,'ACTIVE',%s,%s,%s,CURRENT_TIMESTAMP)
                  ON CONFLICT(device_uuid) DO UPDATE SET device_name=EXCLUDED.device_name,
                    station_id=COALESCE(EXCLUDED.station_id,kiosk_identities.station_id),status='ACTIVE',
                    token_hash=EXCLUDED.token_hash,
                    firmware_version=EXCLUDED.firmware_version,last_ip=EXCLUDED.last_ip,last_seen_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                  RETURNING *, CASE WHEN token_hash=%s THEN TRUE ELSE FALSE END token_replaced""",
                  (device_uuid,str(data.get('device_name') or device_uuid),station_id,token_hash,str(data.get('app_version') or data.get('firmware_version') or ''),last_ip,token_hash))
                row=cur.fetchone()
                # Old firmware needs a token. Reuse is impossible because only hash is stored, so bind rotates token safely.
                return row,token

    def set_status(self,identity_id:int,status:str,station_id=None):
        status=str(status or '').upper()
        if status not in {'PENDING','ACTIVE','DISABLED'}: raise ValueError('invalid kiosk status')
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE kiosk_identities SET status=%s,station_id=COALESCE(%s,station_id),updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(status,station_id,identity_id))
                row=cur.fetchone()
                if not row: raise NotFoundError('kiosk identity not found')
                return row

    def events_for_device(self,device_uuid:str,limit:int=300):
        regular=fetch_all("""SELECT k.*,s.code station_code,e.employee_no,e.name employee_name,o.code operation_code,o.name operation_name
          FROM kiosk_events k LEFT JOIN stations s ON s.id=k.station_id LEFT JOIN employees e ON e.id=k.employee_id LEFT JOIN operations o ON o.id=k.operation_id
          WHERE k.device_uuid=%s ORDER BY k.occurred_at DESC,k.id DESC LIMIT %s""",(device_uuid,min(max(limit,1),1000)))
        offline=fetch_all("""SELECT -id id,client_event_id event_uuid,kiosk_id device_uuid,NULL::bigint station_id,
          'OFFLINE_'||event_type event_type,CASE WHEN status='rejected' THEN 'WARNING' ELSE 'INFO' END severity,
          status,CASE WHEN status='rejected' THEN reason ELSE 'Đồng bộ production event offline' END message,
          payload_json,server_session_id session_id,NULL::bigint operation_id,NULL::bigint employee_id,
          COALESCE(event_time,processed_at,received_at) occurred_at,received_at,processed_at resolved_at,
          NULL::bigint resolved_by,'' resolution_note,'' station_code,'' employee_no,'' employee_name,
          '' operation_code,'' operation_name
          FROM kiosk_client_events WHERE kiosk_id=%s ORDER BY local_sequence DESC LIMIT %s""",
          (device_uuid,min(max(limit,1),1000)))
        rows=[dict(x) for x in regular]+[dict(x) for x in offline]
        rows.sort(key=lambda x:(x.get('occurred_at') is not None,x.get('occurred_at')),reverse=True)
        return rows[:min(max(limit,1),1000)]

class WorkSessionRepository:
    def list_open_for_employee(self,employee_id:int):
        rows=fetch_all("""SELECT ws.id,ws.operation_id,ws.started_at start_time,o.name operation_name,o.qr operation_qr,po.code po,p.code part,''::text session_group_id FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id LEFT JOIN production_orders po ON po.id=o.production_order_id LEFT JOIN parts p ON p.id=o.part_id WHERE ws.employee_id=%s AND ws.status='OPEN' ORDER BY ws.id DESC""",(employee_id,))
        return [dict(x) for x in rows]
    def _replay(self,conn,request_id,action):
        with conn.cursor() as cur:
            cur.execute('SELECT action,response_json FROM kiosk_idempotency WHERE request_id=%s',(request_id,)); row=cur.fetchone()
            if row and str(row.get('action') or '').upper()!=str(action).upper():
                raise ConflictError(f'idempotency key đã được dùng cho action {row.get("action")}')
            return row['response_json'] if row else None
    def start(self,data):
        request_id=str(data.get('request_id','')).strip()
        if not request_id: raise ValueError('request_id required')
        with transaction() as conn:
            with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
            replay=self._replay(conn,request_id,'START')
            if replay is not None: return {**replay,'idempotent_replay':True}
            employee_id=int(data['employee_id']); operation_id=int(data['operation_id'])
            with conn.cursor() as cur:
                cur.execute('SELECT id,active FROM employees WHERE id=%s FOR SHARE',(employee_id,)); emp=cur.fetchone()
                if not emp or not emp['active']: raise RepositoryError('employee inactive or missing')
                operation=lock_startable_operation(cur,operation_id)
                if not operation: raise NotFoundError('operation not found')
                if str(operation.get('po_status') or '').upper()!='IN_PROGRESS':
                    raise ConflictError(f"PO {operation.get('po_code') or ''} chưa Start hoặc đang tạm dừng")
                # Quantity dependency also implies a session dependency.  A downstream
                # operation may not start before the source operation has actually been
                # started by at least one worker.  This prevents the operator from only
                # discovering missing upstream data when finishing the downstream session.
                input_source_id = operation.get('input_source_operation_id') if operation.get('input_flow_enabled') else None
                if input_source_id:
                    cur.execute('''SELECT o.id,o.code,o.name,o.production_order_id,
                                          EXISTS(SELECT 1 FROM work_sessions ws WHERE ws.operation_id=o.id) session_started,
                                          EXISTS(SELECT 1 FROM work_sessions ws WHERE ws.operation_id=o.id AND ws.status='CLOSED') session_reported,
                                          COALESCE(o.done_qty,0) done_qty
                                   FROM operations o WHERE o.id=%s FOR SHARE''',(input_source_id,))
                    source=cur.fetchone()
                    if not source or source['production_order_id']!=operation['production_order_id']:
                        raise ConflictError('OP nguồn đầu vào không hợp lệ')
                    if not source.get('session_started'):
                        raise ConflictError(
                            f"OP nguồn {source.get('code') or input_source_id} chưa bắt đầu session. "
                            f"Phải start session OP nguồn trước khi start {operation.get('code') or operation_id}."
                        )

                # A pure time/order predecessor still requires completion.  When the same
                # operation is also the quantity source, the quantity rule above is used:
                # source session must have started, but the source OP need not be completed.
                predecessor_id=operation.get('predecessor_operation_id')
                if predecessor_id and predecessor_id!=input_source_id:
                    cur.execute('SELECT status,code FROM operations WHERE id=%s',(predecessor_id,)); pred=cur.fetchone()
                    if not pred:raise ConflictError('Operation dependency không tồn tại')
                readiness=dispatch_state_from_db(cur,operation_id)
                if not readiness.get('actionable'):
                    reason=readiness.get('readiness_reason') or 'NOT_READY'
                    raise ConflictError(f"Operation chưa sẵn sàng để Start: {reason}; WIP={readiness.get('wip_qty',0)}")
                cur.execute("SELECT CURRENT_TIMESTAMP now_at")
                now_at=cur.fetchone()['now_at']
                _raise_overlap(_find_employee_session_overlap(cur,employee_id,now_at,None))
                try:
                    cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,start_request_id)
                    VALUES(%s,%s,%s,%s,%s) RETURNING *""",(employee_id,operation_id,data.get('station_id'),str(data.get('device_uuid','')),request_id))
                except Exception as exc:
                    if getattr(exc,'sqlstate',None)=='23505': raise ConflictError('employee already has an open session') from exc
                    raise
                row=cur.fetchone()
                reconcile_operation_and_po(cur,operation_id)
                response=_json_safe({'ok':True,'session':dict(row),'idempotent_replay':False})
                cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'START',Jsonb(response)))
                return response
    def finish(self,session_id,data):
        request_id=str(data.get('request_id','')).strip()
        if not request_id: raise ValueError('request_id required')
        good=max(int(data.get('good_qty',0) or 0),0); defect=max(int(data.get('defect_qty',0) or 0),0); rework=max(int(data.get('rework_qty',0) or 0),0)
        if rework>defect: raise ValueError('rework_qty cannot exceed defect_qty')
        with transaction() as conn:
            with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
            replay=self._replay(conn,request_id,'FINISH')
            if replay is not None: return {**replay,'idempotent_replay':True}
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); row=cur.fetchone()
                if not row: raise NotFoundError('session not found')
                if row['status']!='OPEN': raise ConflictError('session already closed')
                _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=row['operation_id'],good_qty=good,defect_qty=defect)
                cur.execute("SELECT CURRENT_TIMESTAMP now_at")
                finish_at=cur.fetchone()['now_at']
                _raise_overlap(_find_employee_session_overlap(cur,row['employee_id'],row['started_at'],finish_at,session_id))
                cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=%s,good_qty=%s,defect_qty=%s,rework_qty=%s,note=%s,finish_request_id=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(finish_at,good,defect,rework,str(data.get('note','')),request_id,session_id)); closed=cur.fetchone()
                reconcile_operation_and_po(cur,row['operation_id'])
                response=_json_safe({'ok':True,'session':dict(closed),'idempotent_replay':False})
                cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'FINISH',Jsonb(response)))
                return response
    def list(self,limit=200):
        return fetch_all("""SELECT s.*,e.employee_no,e.name employee_name,o.code operation_code,o.name operation_name
        FROM work_sessions s JOIN employees e ON e.id=s.employee_id JOIN operations o ON o.id=s.operation_id
        ORDER BY s.id DESC LIMIT %s""",(limit,))

class QCRepository:
    def start(self,data,user_id):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id,operation_id FROM work_sessions WHERE id=%s FOR SHARE',(int(data['session_id']),)); session=cur.fetchone()
                if not session: raise NotFoundError('session not found')
                cur.execute('INSERT INTO qc_inspections(session_id,operation_id,inspector_user_id) VALUES(%s,%s,%s) RETURNING *',(session['id'],session['operation_id'],user_id)); return cur.fetchone()
    def complete(self,inspection_id,data):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE qc_inspections SET status='COMPLETED',good_qty=%s,defect_qty=%s,defect_reason=%s,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=%s AND status='OPEN' RETURNING *",(max(int(data.get('good_qty',0) or 0),0),max(int(data.get('defect_qty',0) or 0),0),str(data.get('defect_reason','')),inspection_id)); row=cur.fetchone()
                if not row: raise ConflictError('inspection missing or completed')
                return row
    def list(self,limit=200): return fetch_all('SELECT * FROM qc_inspections ORDER BY id DESC LIMIT %s',(limit,))

class SupervisorRepository:
    def adjust(self,session_id,data,user_id):
        good=max(int(data.get('good_qty',0) or 0),0); defect=max(int(data.get('defect_qty',0) or 0),0); rework=max(int(data.get('rework_qty',0) or 0),0); reason=str(data.get('reason','')).strip()
        if rework>defect: raise ValueError('rework_qty cannot exceed defect_qty')
        if not reason: raise ValueError('reason required')
        request_id=str(data.get('request_id') or '').strip()
        with transaction() as conn:
            if request_id:
                with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
                replay=WorkSessionRepository()._replay(conn,request_id,'SESSION_ADJUST')
                if replay is not None:return replay
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); row=cur.fetchone()
                if not row: raise NotFoundError('session not found')
                if row['status']=='CLOSED':
                    _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=row['operation_id'],good_qty=good,defect_qty=defect,origin='ADMIN_EDIT')
                cur.execute('UPDATE work_sessions SET good_qty=%s,defect_qty=%s,rework_qty=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(good,defect,rework,session_id))
                reconcile_operation_and_po(cur,row['operation_id'])
                cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,old_defect_qty,new_defect_qty,old_rework_qty,new_rework_qty,reason,adjusted_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(session_id,row['operation_id'],row['good_qty'],good,row['defect_qty'],defect,int(row.get('rework_qty') or 0),rework,reason,user_id)); result=_json_safe(dict(cur.fetchone()))
                if request_id:cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'SESSION_ADJUST',Jsonb(result)))
                return result
    def edit_session(self,session_id,data,user_id):
        reason=str(data.get('reason') or '').strip()
        if not reason: raise ValueError('Phải nhập lý do chỉnh sửa session')
        request_id=str(data.get('request_id') or '').strip()
        with transaction() as conn:
            if request_id:
                with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
                replay=WorkSessionRepository()._replay(conn,request_id,'SESSION_EDIT')
                if replay is not None:return replay
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); old=cur.fetchone()
                if not old: raise NotFoundError('session not found')
                employee_id=int(data.get('employee_id') or old['employee_id'])
                operation_id=int(data.get('operation_id') or old['operation_id'])
                station_id=data.get('station_id',old['station_id']); station_id=int(station_id) if station_id not in (None,'') else None
                status=str(data.get('status') or old['status']).upper()
                if status not in ('OPEN','CLOSED'): raise ValueError('Trạng thái session không hợp lệ')
                started_at=data.get('started_at') or old['started_at']
                ended_at=data.get('ended_at')
                if status=='OPEN': ended_at=None
                elif not ended_at: ended_at=old['ended_at'] or started_at
                good=max(int(data.get('good_qty',old['good_qty']) or 0),0); defect=max(int(data.get('defect_qty',old['defect_qty']) or 0),0); rework=max(int(data.get('rework_qty',old.get('rework_qty',0)) or 0),0)
                if rework>defect: raise ValueError('rework_qty cannot exceed defect_qty')
                note=str(data.get('note',old.get('note') or ''))
                cur.execute('SELECT 1 FROM employees WHERE id=%s AND active=TRUE',(employee_id,))
                if not cur.fetchone(): raise ValueError('Nhân viên không tồn tại hoặc đã khóa')
                cur.execute('SELECT status,code FROM operations WHERE id=%s FOR UPDATE',(operation_id,)); target_operation=cur.fetchone()
                if not target_operation: raise ValueError('Operation không tồn tại')
                if status=='OPEN' and target_operation and str(target_operation.get('status') or '').upper()=='CANCELLED':
                    raise ConflictError(f"Operation {target_operation.get('code') or operation_id} đã CANCELLED, không thể reopen session")
                cur.execute('SELECT %s::timestamptz st,%s::timestamptz en',(started_at,ended_at)); times=cur.fetchone()
                if times['en'] is not None and times['en'] < times['st']: raise ValueError('Giờ kết thúc phải sau giờ bắt đầu')
                _raise_overlap(_find_employee_session_overlap(cur,employee_id,times['st'],times['en'],session_id))
                if status=='CLOSED':
                    _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=operation_id,good_qty=good,defect_qty=defect,origin='ADMIN_EDIT')
                else:
                    cur.execute('DELETE FROM operation_input_consumptions WHERE session_id=%s',(session_id,))
                cur.execute("""UPDATE work_sessions SET employee_id=%s,operation_id=%s,station_id=%s,status=%s,started_at=%s::timestamptz,ended_at=%s::timestamptz,good_qty=%s,defect_qty=%s,rework_qty=%s,note=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *""",(employee_id,operation_id,station_id,status,started_at,ended_at,good,defect,rework,note,session_id)); new=cur.fetchone()
                cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,old_defect_qty,new_defect_qty,old_rework_qty,new_rework_qty,reason,adjusted_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(session_id,operation_id,old['good_qty'],good,old['defect_qty'],defect,int(old.get('rework_qty') or 0),rework,reason,user_id))
                reconcile_operation_and_po(cur,old['operation_id'])
                if int(old['operation_id'])!=operation_id:
                    reconcile_operation_and_po(cur,operation_id)
                result=_json_safe({'old':dict(old),'item':dict(new),'reason':reason})
                if request_id:cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'SESSION_EDIT',Jsonb(result)))
                return result

    def penalty(self,data,user_id):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO penalty_tickets(employee_id,operation_id,session_id,points,reason,issued_by)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",(int(data['employee_id']),data.get('operation_id'),data.get('session_id'),int(data.get('points',0) or 0),str(data.get('reason','')),user_id)); return cur.fetchone()
