from __future__ import annotations
import hashlib,secrets
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from psycopg.types.json import Jsonb
from typing import Any
from mesflow.db.connection import transaction,fetch_all,fetch_one
from .base import NotFoundError,ConflictError,RepositoryError
from .production_state import lock_idempotency_key,lock_startable_operation,reconcile_operation_and_po,lock_production_order_for_operation_first
from .scheduling import dispatch_state_from_db
from mesflow.domain.audit import record_audit
from mesflow.domain.trace import record_event,record_quantities
from mesflow.core.time_policy import trusted_event_time


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
                cur.execute("SELECT boot_id,boot_seen_at,boot_seen_at>CURRENT_TIMESTAMP-INTERVAL '15 minutes' boot_recent FROM kiosk_identities WHERE device_uuid=%s AND status='ACTIVE' FOR UPDATE",(device_uuid,))
                previous_boot=cur.fetchone() or {};new_boot=str(data.get('boot_id') or '')[:120]
                boot_loop=bool(new_boot and previous_boot.get('boot_id') and new_boot!=previous_boot.get('boot_id') and previous_boot.get('boot_recent') and int(data.get('uptime_seconds',0) or 0)<300)
                cur.execute("""UPDATE kiosk_identities SET firmware_version=%s,firmware_build=%s,hardware_model=%s,
                               ota_capable=%s,boot_id=%s,uptime_seconds=%s,boot_reason=%s,
                               boot_seen_at=CASE WHEN boot_id<>%s AND %s<>'' THEN CURRENT_TIMESTAMP ELSE boot_seen_at END,
                               last_seen_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                               WHERE device_uuid=%s AND status='ACTIVE' RETURNING station_id""",
                            (str(data.get('firmware_version') or data.get('app_version') or ''),str(data.get('firmware_build') or ''),
                             str(data.get('hardware_model') or ''),bool(data.get('ota_capable',False)),new_boot,int(data.get('uptime_seconds',0) or 0),
                             str(data.get('boot_reason') or '')[:120],new_boot,new_boot,device_uuid))
                identity=cur.fetchone()
                if not identity: raise NotFoundError('active kiosk identity not found')
                cur.execute("""INSERT INTO kiosk_status(device_uuid,station_id,ui_state,health_state,queue_size,wifi_rssi,free_heap,last_error,last_heartbeat_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                ON CONFLICT(device_uuid) DO UPDATE SET station_id=EXCLUDED.station_id,ui_state=EXCLUDED.ui_state,
                health_state=EXCLUDED.health_state,queue_size=EXCLUDED.queue_size,wifi_rssi=EXCLUDED.wifi_rssi,
                free_heap=EXCLUDED.free_heap,last_error=EXCLUDED.last_error,last_heartbeat_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                RETURNING *""",(device_uuid,identity['station_id'],str(data.get('ui_state','UNKNOWN')),str(data.get('health_state','OK')),int(data.get('queue_size',0) or 0),data.get('wifi_rssi'),data.get('free_heap'),'OTA_BOOT_LOOP_SUSPECTED' if boot_loop else str(data.get('last_error',''))))
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
                cur.execute("SELECT status FROM kiosk_identities WHERE device_uuid=%s FOR UPDATE",(device_uuid,))
                existing=cur.fetchone()
                if existing and str(existing.get('status') or '').upper()!='ACTIVE':
                    from mesflow.domain.errors import PermissionDeniedError
                    raise PermissionDeniedError(
                        f"Kiosk '{device_uuid}' đang ở trạng thái {existing.get('status')} -- chỉ quản trị viên mới có thể kích hoạt lại."
                    )
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
        generation=fetch_one("SELECT cluster_id,generation_id,bumped_at,bumped_by,reason FROM server_generation WHERE id=1") or {}
        summary=fetch_one("""SELECT
          COUNT(*) identity_count,
          COUNT(*) FILTER (WHERE ki.status='PENDING') pending_count,
          COUNT(*) FILTER (WHERE ki.status='ACTIVE') active_count,
          COUNT(*) FILTER (WHERE ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes') online_count,
          COUNT(*) FILTER (WHERE ks.last_error<>'' OR ks.health_state IN ('ERROR','DEGRADED')) error_count,
          (SELECT COUNT(*) FROM kiosk_client_events WHERE status='rejected') offline_conflict_count,
          COUNT(*) FILTER (WHERE ki.status='ACTIVE' AND ki.last_generation_id<>'' AND ki.last_generation_id<>(SELECT generation_id FROM server_generation WHERE id=1)) reconciling_count
        FROM kiosk_identities ki LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid""") or {}
        kiosks=fetch_all("""SELECT ki.id,ki.device_uuid,ki.device_name,ki.station_id,ki.status,ki.firmware_version,ki.last_ip,ki.last_seen_at,ki.created_at,
          ki.last_sequence_received,ki.duplicate_replay_count,ki.last_generation_id,
          s.code station_code,s.name station_name,s.workshop,s.production_line,
          ks.ui_state,ks.health_state,ks.queue_size,ks.wifi_rssi,ks.free_heap,ks.last_error,ks.last_heartbeat_at,
          CASE WHEN ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes' THEN TRUE ELSE FALSE END online,
          CASE WHEN ki.status='ACTIVE' AND ki.last_generation_id<>'' AND ki.last_generation_id<>%s THEN TRUE ELSE FALSE END generation_stale,
          (SELECT COUNT(*) FROM kiosk_events ke WHERE ke.device_uuid=ki.device_uuid AND ke.status='OPEN' AND ke.severity IN ('ERROR','CRITICAL')) open_error_count,
          (SELECT MAX(ke.occurred_at) FROM kiosk_events ke WHERE ke.device_uuid=ki.device_uuid) last_event_at,
          (SELECT COUNT(*) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid AND ce.status='accepted') offline_synced_count,
          (SELECT COUNT(*) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid AND ce.status='rejected') offline_conflict_count,
          (SELECT COUNT(*) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid AND ce.source='RECONCILE_REPLAY') reconcile_replay_count,
          (SELECT MAX(ce.processed_at) FROM kiosk_client_events ce WHERE ce.kiosk_id=ki.device_uuid) last_offline_sync_at
        FROM kiosk_identities ki LEFT JOIN stations s ON s.id=ki.station_id LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
        ORDER BY online DESC,open_error_count DESC,ki.status,ki.device_name,ki.device_uuid""",(generation.get('generation_id',''),))
        return {'summary':dict(summary),'kiosks':[dict(x) for x in kiosks],'generation':dict(generation)}

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
                cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,station_id,status,token_hash,firmware_version,firmware_build,hardware_model,ota_capable,last_ip,last_seen_at)
                  VALUES(%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                  ON CONFLICT(device_uuid) DO UPDATE SET device_name=EXCLUDED.device_name,
                    station_id=COALESCE(EXCLUDED.station_id,kiosk_identities.station_id),status='ACTIVE',
                    token_hash=EXCLUDED.token_hash,
                    firmware_version=EXCLUDED.firmware_version,firmware_build=EXCLUDED.firmware_build,
                    hardware_model=EXCLUDED.hardware_model,ota_capable=EXCLUDED.ota_capable,
                    last_ip=EXCLUDED.last_ip,last_seen_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                  RETURNING *, CASE WHEN token_hash=%s THEN TRUE ELSE FALSE END token_replaced""",
                  (device_uuid,str(data.get('device_name') or device_uuid),station_id,token_hash,
                   str(data.get('app_version') or data.get('firmware_version') or ''),str(data.get('firmware_build') or ''),
                   str(data.get('hardware_model') or ''),bool(data.get('ota_capable',False)),last_ip,token_hash))
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
    def start(self,data,audit_actor_username='',audit_actor_user_id=None,audit_correlation_id=''):
        request_id=str(data.get('request_id','')).strip()
        if not request_id: raise ValueError('request_id required')
        # Reliability Validation Round 2, FIX 2: opt-in stage timing
        # (MESFLOW_TIMING_DEBUG=1) to profile the write-path concurrency
        # ceiling Gate 13 found -- see core/timing_debug.py's own docstring.
        # No-op, near-zero overhead when disabled (the default).
        from mesflow.core.timing_debug import StageTimer
        timer=StageTimer('session_start')
        with transaction() as conn:
            with timer.stage('idempotency_lock_and_replay'):
                with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
                replay=self._replay(conn,request_id,'START')
            if replay is not None:
                timer.emit(request_id=request_id,idempotent_replay=True)
                return {**replay,'idempotent_replay':True}
            employee_id=int(data['employee_id']); operation_id=int(data['operation_id'])
            with conn.cursor() as cur:
                with timer.stage('lock_po_first'):
                    # MUST be the very first row lock this transaction takes --
                    # see lock_production_order_for_operation_first()'s own
                    # docstring for the confirmed-live deadlock this prevents.
                    lock_production_order_for_operation_first(cur,operation_id)
                with timer.stage('employee_check'):
                    cur.execute('SELECT id,active FROM employees WHERE id=%s FOR SHARE',(employee_id,)); emp=cur.fetchone()
                    if not emp or not emp['active']: raise RepositoryError('employee inactive or missing')
                with timer.stage('lock_operation_and_po'):
                    # This is the PO-row-serialization hot spot: reconcile_operation_and_po()
                    # (called from lock_startable_operation -> reconcile_operation ->
                    # reconcile_production_order) takes FOR UPDATE on the SHARED parent
                    # production_orders row -- every concurrent start()/finish() for ANY
                    # operation under the same PO serializes here, one at a time.
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
                with timer.stage('readiness_check'):
                    readiness=dispatch_state_from_db(cur,operation_id)
                    if not readiness.get('actionable'):
                        reason=readiness.get('readiness_reason') or 'NOT_READY'
                        raise ConflictError(f"Operation chưa sẵn sàng để Start: {reason}; WIP={readiness.get('wip_qty',0)}")
                cur.execute("SELECT CURRENT_TIMESTAMP now_at")
                now_at=cur.fetchone()['now_at']
                # `occurred_at`, when present, is a Python
                # datetime already produced by a trusted source (currently
                # only OfflineSyncRepository, via time_policy.trusted_event_time()
                # against the device's own time_quality=='synced' clock) --
                # never a raw HTTP body field (no route passes user input
                # through this key; see web/kiosk.py's/execution.py's explicit
                # payload whitelists). Re-validated here anyway, defensively,
                # so a future caller can't accidentally create an impossible
                # started_at by passing something unvetted.
                started_at=trusted_event_time(data.get('occurred_at'),'synced',server_now=now_at) if data.get('occurred_at') is not None else None
                started_at_trusted=started_at is not None
                if started_at is None: started_at=now_at
                with timer.stage('employee_overlap_query'):
                    _raise_overlap(_find_employee_session_overlap(cur,employee_id,started_at,None))
                with timer.stage('session_insert'):
                    try:
                        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,start_request_id,started_at,started_at_trusted)
                        VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(employee_id,operation_id,data.get('station_id'),str(data.get('device_uuid','')),request_id,started_at,started_at_trusted))
                    except Exception as exc:
                        if getattr(exc,'sqlstate',None)=='23505': raise ConflictError('employee already has an open session') from exc
                        raise
                    row=cur.fetchone()
                with timer.stage('reconcile_operation_and_po'):
                    reconcile_operation_and_po(cur,operation_id)
                response=_json_safe({'ok':True,'session':dict(row),'idempotent_replay':False})
                with timer.stage('idempotency_insert'):
                    cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'START',Jsonb(response)))
                # V66: transactionally-consistent audit row -- same cursor/commit as the
                # INSERT above, so a session can never exist without a matching audit
                # entry (or vice versa). audit_actor_* defaults keep kiosk/device callers
                # (which have no web user session) working unchanged.
                with timer.stage('audit_and_event'):
                    record_audit(cur,action='SESSION_STARTED',entity_type='work_session',entity_id=str(row['id']),
                        actor_username=audit_actor_username,actor_user_id=audit_actor_user_id,employee_id=employee_id,
                        correlation_id=audit_correlation_id or request_id,after=response['session'],source='mesflow.web')
                    record_event(cur,event_type='SESSION_STARTED',category='SESSION',title='Session bắt đầu',operation_id=operation_id,
                        session_id=row['id'],actor_id=audit_actor_user_id,actor_name=audit_actor_username,correlation_id=audit_correlation_id or request_id,
                        metadata={'employee_id':employee_id,'request_id':request_id})
                timer.emit(request_id=request_id,session_id=row['id'],operation_id=operation_id,idempotent_replay=False)
                return response
    def _finish_within(self,conn,session_id,data,audit_actor_username='',audit_actor_user_id=None,audit_correlation_id=''):
        """The real body of finish(), operating on an ALREADY-OPEN
        connection/transaction -- factored out so
        finish_many() can drive several sessions' worth of this under ONE
        shared transaction (true atomicity: all-or-nothing across the whole
        batch) instead of each finish() call committing independently,
        which is exactly the "OP1 committed, OP2 failed, API tổng thể trả
        error" partial-write bug this avoids. finish() below is
        now a one-line wrapper: open a transaction, call this once, done --
        every existing single-item caller is unaffected."""
        request_id=str(data.get('request_id','')).strip()
        if not request_id: raise ValueError('request_id required')
        good=max(int(data.get('good_qty',0) or 0),0); defect=max(int(data.get('defect_qty',0) or 0),0); rework=max(int(data.get('rework_qty',0) or 0),0)
        if rework>defect: raise ValueError('rework_qty cannot exceed defect_qty')
        # Reliability Validation Round 2, FIX 2: same opt-in timing as
        # start() above -- see core/timing_debug.py. For finish_many()'s
        # batch case, this timer's "total_ms" only covers ITS OWN item
        # (the shared connection/transaction was already open before this
        # call), so it excludes connection-acquisition time for every item
        # after the first in a batch -- noted rather than papered over.
        from mesflow.core.timing_debug import StageTimer
        timer=StageTimer('session_finish')
        with timer.stage('idempotency_lock_and_replay'):
            with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
            replay=self._replay(conn,request_id,'FINISH')
        if replay is not None:
            timer.emit(request_id=request_id,session_id=session_id,idempotent_replay=True)
            return {**replay,'idempotent_replay':True}
        with conn.cursor() as cur:
            with timer.stage('lock_po_first'):
                # MUST be the very first row lock this transaction takes --
                # see lock_production_order_for_operation_first()'s own
                # docstring for the confirmed-live deadlock this prevents.
                # A plain, unlocked lookup first (session_id doesn't tell us
                # operation_id yet) -- if the session doesn't exist this
                # returns None and the FOR UPDATE lookup right below raises
                # the real NotFoundError, same as before.
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if pre: lock_production_order_for_operation_first(cur,pre['operation_id'])
            with timer.stage('lock_session_and_input_consumption'):
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); row=cur.fetchone()
                if not row: raise NotFoundError('session not found')
                if row['status']!='OPEN': raise ConflictError('session already closed')
                _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=row['operation_id'],good_qty=good,defect_qty=defect)
            cur.execute("SELECT CURRENT_TIMESTAMP now_at")
            server_now=cur.fetchone()['now_at']
            # Same trusted-timestamp handling as start()
            # above. A trusted ended_at that would land at/before started_at
            # (e.g. a device's own start/finish events raced or its clock
            # jumped between the two) is NOT used -- falls back to server
            # time rather than writing an impossible-duration session.
            finish_at=trusted_event_time(data.get('occurred_at'),'synced',server_now=server_now) if data.get('occurred_at') is not None else None
            ended_at_trusted=finish_at is not None and finish_at>row['started_at']
            if not ended_at_trusted: finish_at=server_now
            with timer.stage('employee_overlap_query'):
                _raise_overlap(_find_employee_session_overlap(cur,row['employee_id'],row['started_at'],finish_at,session_id))
            with timer.stage('record_quantities_and_session_update'):
                movements=record_quantities(cur,session=row,good=good,defect=defect,rework=rework,actor_id=audit_actor_user_id,
                    actor_name=audit_actor_username,source='SESSION_FINISH',reason=str(data.get('note','')),correlation_id=audit_correlation_id or request_id)
                cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=%s,ended_at_trusted=%s,good_qty=%s,defect_qty=%s,rework_qty=%s,note=%s,finish_request_id=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(finish_at,ended_at_trusted,good,defect,rework,str(data.get('note','')),request_id,session_id)); closed=cur.fetchone()
            with timer.stage('reconcile_operation_and_po'):
                # Same PO-row-serialization hot spot as start() -- see its
                # comment above lock_startable_operation().
                reconcile_operation_and_po(cur,row['operation_id'])
            response=_json_safe({'ok':True,'session':dict(closed),'idempotent_replay':False})
            with timer.stage('idempotency_insert'):
                cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'FINISH',Jsonb(response)))
            # V66: transactionally-consistent audit row, same cursor/commit as the
            # UPDATE above -- see start() for the same rationale. before=the OPEN
            # session snapshot captured under FOR UPDATE at the top of this method.
            with timer.stage('audit_and_events'):
                record_audit(cur,action='SESSION_FINISHED',entity_type='work_session',entity_id=str(session_id),
                    actor_username=audit_actor_username,actor_user_id=audit_actor_user_id,employee_id=row['employee_id'],
                    correlation_id=audit_correlation_id or request_id,before=_json_safe(dict(row)),after=response['session'],source='mesflow.web')
                for movement in movements:
                    record_event(cur,event_type={'GOOD':'GOOD_QUANTITY_RECORDED','DEFECT':'DEFECT_QUANTITY_RECORDED','REPAIRABLE':'REPAIRABLE_DEFECT_RECORDED'}[movement['movement_type']],
                      category={'GOOD':'QUANTITY','DEFECT':'DEFECT','REPAIRABLE':'REWORK'}[movement['movement_type']],title={'GOOD':'Ghi nhận sản lượng đạt','DEFECT':'Ghi nhận sản lượng lỗi','REPAIRABLE':'Ghi nhận lỗi sửa được'}[movement['movement_type']],
                      operation_id=row['operation_id'],session_id=session_id,actor_id=audit_actor_user_id,actor_name=audit_actor_username,quantity_delta=movement['delta'],correlation_id=audit_correlation_id or request_id,metadata={'movement_id':movement['id']})
                record_event(cur,event_type='SESSION_FINISHED',category='SESSION',title='Session kết thúc',operation_id=row['operation_id'],session_id=session_id,
                    actor_id=audit_actor_user_id,actor_name=audit_actor_username,correlation_id=audit_correlation_id or request_id,occurred_at=finish_at,
                    metadata={'good':good,'defect':defect,'repairable':rework,'request_id':request_id})
            timer.emit(request_id=request_id,session_id=session_id,operation_id=row['operation_id'],idempotent_replay=False)
            return response

    def finish(self,session_id,data,audit_actor_username='',audit_actor_user_id=None,audit_correlation_id=''):
        with transaction() as conn:
            return self._finish_within(conn,session_id,data,audit_actor_username,audit_actor_user_id,audit_correlation_id)

    def finish_many(self,items,audit_actor_username='',audit_actor_user_id=None,audit_correlation_id=''):
        """Atomic batch finish for /session/group/finish --
        ALL items succeed or the WHOLE transaction rolls back (a single
        `with transaction()` shared across every item, via _finish_within()),
        never a partial commit with some sessions closed and others not.
        `items`: list of (session_id, data) tuples, data shaped like
        finish()'s own `data` param (request_id/good_qty/defect_qty/
        rework_qty/note per item). Returns the list of per-item responses in
        the SAME order as `items` -- raises (and rolls back everything) on
        the first item that fails: a true atomic batch, not a
        partial-result/recovery-semantics design."""
        with transaction() as conn:
            return [self._finish_within(conn,session_id,data,audit_actor_username,audit_actor_user_id,audit_correlation_id)
                    for session_id,data in items]
    def list(self,limit=200):
        return fetch_all("""SELECT s.*,e.employee_no,e.name employee_name,o.code operation_code,o.name operation_name
        FROM work_sessions s JOIN employees e ON e.id=s.employee_id JOIN operations o ON o.id=s.operation_id
        ORDER BY s.id DESC LIMIT %s""",(limit,))

    def auto_close_for_shift_end(self,session_id:int,shift_end_at,correlation_id:str=''):
        """A DEDICATED auto-close
        lifecycle -- deliberately NOT a thin wrapper around
        `finish(good_qty=0,...)`, since finish() conflates quantity entry/input-consumption
        validation/reconciliation/audit/domain-events for a REAL operator
        action with what an unattended system boundary-crossing needs).

        Keeps whatever good/defect/rework the session already had (never
        invents a number -- `record_quantities()` records zero movements
        when nothing changed, so this never fabricates a quantity_movements
        row either), reconciles Operation/PO from the resulting CLOSED
        fact, and marks close_reason/closed_by_system/shift_boundary_used_at
        (migration 0040) so an auto-closed session is queryable/auditable
        as distinct from a real operator finish -- SESSION_AUTO_CLOSED is a
        separate domain event type from SESSION_FINISHED, never disguised
        as a manual finish.

        Idempotent + concurrency-safe (Phase 3): an advisory xact lock
        keyed per session_id serializes two reconciliation runs racing on
        the SAME session (the same pattern lock_idempotency_key() uses for
        START/FINISH's request_id); if the session is no longer OPEN by the
        time the lock is acquired (already manually finished, or already
        auto-closed by a run that got there first), this is a no-op
        returning None -- callers (ShiftSessionReconciliationService) must
        treat None as "nothing to do", never as an error.
        """
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,1))',(f'auto-close-session-{session_id}',))
                # Same PO-lock-first requirement as start()/finish() -- see
                # lock_production_order_for_operation_first()'s docstring.
                # The reconciliation service can run several sessions
                # concurrently (Phase 3 concurrency-safety), so this is not
                # theoretical here either.
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if pre: lock_production_order_for_operation_first(cur,pre['operation_id'])
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,))
                row=cur.fetchone()
                if not row:
                    return None
                if row['status']!='OPEN':
                    return None
                if shift_end_at<=row['started_at']:
                    raise ValueError(f'shift_end_at {shift_end_at} is not after session #{session_id} started_at {row["started_at"]}')
                good=int(row.get('good_qty') or 0);defect=int(row.get('defect_qty') or 0);rework=int(row.get('rework_qty') or 0)
                # Same overlap guard finish() applies -- auto-close must not
                # silently create a time-range conflict finish() itself
                # would have refused.
                _raise_overlap(_find_employee_session_overlap(cur,row['employee_id'],row['started_at'],shift_end_at,session_id))
                # Mirrors finish()'s own input-consumption upsert (kept
                # consistent even though quantities aren't changing here) so
                # an auto-closed session's ledger row is never silently
                # stale/missing relative to a manually-finished one.
                _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=row['operation_id'],good_qty=good,defect_qty=defect,origin='AUTO_SHIFT_CLOSE')
                record_quantities(cur,session=row,good=good,defect=defect,rework=rework,actor_id=None,actor_name='SYSTEM',
                    source='AUTO_SHIFT_CLOSE',reason='Tự động đóng ca vào cuối giờ làm việc',correlation_id=correlation_id)
                # quantity_confirmed=FALSE: a human never confirmed the final
                # numbers for THIS close (see migration 0042) -- even if
                # good/defect already carry some real value from earlier in
                # the shift, nobody has looked at and confirmed them as the
                # session's true final result. ReportRepository.session_
                # exceptions() surfaces this as AUTO_CLOSED_UNCONFIRMED until
                # an admin/supervisor correction (adjust()/edit_session())
                # flips it back TRUE.
                cur.execute("""UPDATE work_sessions SET status='CLOSED',ended_at=%s,good_qty=%s,defect_qty=%s,rework_qty=%s,
                    close_reason='AUTO_SHIFT_END',closed_by_system=TRUE,shift_boundary_used_at=%s,
                    quantity_confirmed=FALSE,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s RETURNING *""",(shift_end_at,good,defect,rework,shift_end_at,session_id))
                closed=cur.fetchone()
                reconcile_operation_and_po(cur,row['operation_id'])
                response=_json_safe({'ok':True,'session':dict(closed),'auto_closed':True})
                record_audit(cur,action='SESSION_AUTO_CLOSED',entity_type='work_session',entity_id=str(session_id),
                    actor_username='SYSTEM',actor_user_id=None,employee_id=row['employee_id'],correlation_id=correlation_id,
                    before=_json_safe(dict(row)),after=response['session'],source='shift-reconciliation',
                    metadata={'shift_end_at':shift_end_at.isoformat() if hasattr(shift_end_at,'isoformat') else str(shift_end_at)})
                record_event(cur,event_type='SESSION_AUTO_CLOSED',category='SESSION',title='Session tự động đóng ca',
                    operation_id=row['operation_id'],session_id=session_id,actor_name='SYSTEM',correlation_id=correlation_id,
                    occurred_at=shift_end_at,metadata={'close_reason':'AUTO_SHIFT_END','good':good,'defect':defect,'rework':rework})
                return response

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
                # Same PO-lock-first requirement as WorkSessionRepository's
                # start()/finish() -- see
                # lock_production_order_for_operation_first()'s docstring.
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if pre: lock_production_order_for_operation_first(cur,pre['operation_id'])
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); row=cur.fetchone()
                if not row: raise NotFoundError('session not found')
                if row['status']=='CLOSED':
                    _validate_and_upsert_input_consumption(cur,session_id=session_id,target_operation_id=row['operation_id'],good_qty=good,defect_qty=defect,origin='ADMIN_EDIT')
                cur.execute('SELECT username FROM users WHERE id=%s',(user_id,));actor_row=cur.fetchone();actor_name=(actor_row or {}).get('username','')
                movements=record_quantities(cur,session=row,good=good,defect=defect,rework=rework,actor_id=user_id,actor_name=actor_name,source='CORRECTION',reason=reason,correlation_id=request_id)
                # An explicit admin/supervisor correction IS the human
                # confirmation this session was missing (spec section 2/4) --
                # always flips quantity_confirmed back TRUE, whatever it was
                # before (see migration 0042).
                cur.execute('UPDATE work_sessions SET good_qty=%s,defect_qty=%s,rework_qty=%s,quantity_confirmed=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(good,defect,rework,session_id))
                reconcile_operation_and_po(cur,row['operation_id'])
                cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,old_defect_qty,new_defect_qty,old_rework_qty,new_rework_qty,reason,adjusted_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(session_id,row['operation_id'],row['good_qty'],good,row['defect_qty'],defect,int(row.get('rework_qty') or 0),rework,reason,user_id)); result=_json_safe(dict(cur.fetchone()))
                record_event(cur,event_type='VALUE_CHANGED',category='CHANGE',title='Điều chỉnh sản lượng Session',description=reason,operation_id=row['operation_id'],session_id=session_id,actor_id=user_id,actor_name=actor_name,correlation_id=request_id,metadata={'adjustment_id':result['id'],'movements':[x['id'] for x in movements]})
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
                cur.execute('SELECT username FROM users WHERE id=%s',(user_id,));actor_row=cur.fetchone();actor_name=(actor_row or {}).get('username','')
                movements=record_quantities(cur,session=old,good=good,defect=defect,rework=rework,actor_id=user_id,actor_name=actor_name,source='CORRECTION',reason=reason,correlation_id=request_id)
                # Same confirmation rule as adjust() above.
                cur.execute("""UPDATE work_sessions SET employee_id=%s,operation_id=%s,station_id=%s,status=%s,started_at=%s::timestamptz,ended_at=%s::timestamptz,good_qty=%s,defect_qty=%s,rework_qty=%s,note=%s,quantity_confirmed=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *""",(employee_id,operation_id,station_id,status,started_at,ended_at,good,defect,rework,note,session_id)); new=cur.fetchone()
                cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,old_defect_qty,new_defect_qty,old_rework_qty,new_rework_qty,reason,adjusted_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(session_id,operation_id,old['good_qty'],good,old['defect_qty'],defect,int(old.get('rework_qty') or 0),rework,reason,user_id))
                reconcile_operation_and_po(cur,old['operation_id'])
                if int(old['operation_id'])!=operation_id:
                    reconcile_operation_and_po(cur,operation_id)
                result=_json_safe({'old':dict(old),'item':dict(new),'reason':reason})
                record_event(cur,event_type='VALUE_CHANGED',category='CHANGE',title='Chỉnh sửa Session',description=reason,operation_id=operation_id,session_id=session_id,actor_id=user_id,actor_name=actor_name,correlation_id=request_id,metadata={'before':_json_safe(dict(old)),'after':_json_safe(dict(new)),'movement_ids':[x['id'] for x in movements]})
                if request_id:cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'SESSION_EDIT',Jsonb(result)))
                return result

    def transfer_operation(self,session_id,data,user_id,actor_role=''):
        """Chuyen Operation (spec section 6): a DEDICATED action, deliberately
        separate from edit_session()'s generic field-by-field form. Operation
        is the one field where a wrong click has outsized consequences --
        the session's quantities silently start counting toward a different
        Part/PO's progress -- so it gets its own confirm step and its own
        validation instead of riding along inside an ordinary time/quantity
        correction.

        Rules (spec section 6): new Operation must exist and not be
        CANCELLED; same-Part transfers are always allowed; a cross-Part
        transfer (still same PO) requires the caller to have explicitly
        confirmed (confirm_cross_part=true) -- never silently allowed; a
        cross-PO transfer is blocked unless the actor is 'admin' (this
        RBAC's highest role -- there is no separate finer-grained permission
        for it, see AGENTS.md's real role list).
        """
        new_operation_id=int(data.get('operation_id') or 0)
        if not new_operation_id: raise ValueError('Chưa chọn Operation mới')
        reason=str(data.get('reason') or '').strip()
        if not reason: raise ValueError('Phải nhập lý do chuyển Operation')
        confirm_cross_part=bool(data.get('confirm_cross_part'))
        request_id=str(data.get('request_id') or '').strip()
        with transaction() as conn:
            if request_id:
                with conn.cursor() as cur: lock_idempotency_key(cur,request_id)
                replay=WorkSessionRepository()._replay(conn,request_id,'SESSION_OPERATION_TRANSFER')
                if replay is not None:return replay
            with conn.cursor() as cur:
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if not pre: raise NotFoundError('session not found')
                cur.execute('SELECT production_order_id FROM operations WHERE id=%s',(pre['operation_id'],)); src_ref=cur.fetchone()
                if not src_ref: raise NotFoundError('session not found')
                cur.execute('SELECT production_order_id FROM operations WHERE id=%s',(new_operation_id,)); tgt_ref=cur.fetchone()
                if not tgt_ref: raise ValueError('Operation không tồn tại')
                # Lock every PO involved, in a FIXED (ascending id) order --
                # same deadlock-avoidance reasoning as
                # lock_production_order_for_operation_first()'s own docstring,
                # generalized to the (rare, admin-only) two-different-PO case
                # a reverse concurrent transfer could otherwise deadlock on.
                for po_id in sorted({src_ref['production_order_id'],tgt_ref['production_order_id']}):
                    cur.execute('SELECT id FROM production_orders WHERE id=%s FOR UPDATE',(po_id,))
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); old=cur.fetchone()
                if not old: raise NotFoundError('session not found')
                if int(old['operation_id'])==new_operation_id: raise ValueError('Operation mới trùng Operation hiện tại')
                cur.execute("""SELECT o.id,o.code,o.name,o.status,o.part_id,o.production_order_id,p.code part_code,
                    po.code po_code FROM operations o JOIN parts p ON p.id=o.part_id
                    JOIN production_orders po ON po.id=o.production_order_id WHERE o.id=%s FOR UPDATE OF o""",(old['operation_id'],))
                source_op=cur.fetchone()
                cur.execute("""SELECT o.id,o.code,o.name,o.status,o.part_id,o.production_order_id,p.code part_code,
                    po.code po_code FROM operations o JOIN parts p ON p.id=o.part_id
                    JOIN production_orders po ON po.id=o.production_order_id WHERE o.id=%s FOR UPDATE OF o""",(new_operation_id,))
                target_op=cur.fetchone()
                if not target_op: raise ValueError('Operation không tồn tại')
                if str(target_op.get('status') or '').upper()=='CANCELLED':
                    raise ConflictError(f"Operation {target_op.get('code') or new_operation_id} đã CANCELLED, không thể chuyển vào")
                if int(target_op['production_order_id'])!=int(source_op['production_order_id']):
                    if str(actor_role or '').lower()!='admin':
                        raise ConflictError(f"Operation mới thuộc PO khác ({target_op.get('po_code')} khác {source_op.get('po_code')}); chỉ admin mới được chuyển khác PO")
                elif int(target_op['part_id'])!=int(source_op['part_id']) and not confirm_cross_part:
                    raise ConflictError(f"Operation mới thuộc Part khác ({target_op.get('part_code')} khác {source_op.get('part_code')}); cần xác nhận rõ trước khi chuyển")
                cur.execute('SELECT username FROM users WHERE id=%s',(user_id,));actor_row=cur.fetchone();actor_name=(actor_row or {}).get('username','')
                # Time and good/reject quantities stay exactly as they were --
                # only the Operation assignment (and, transitively, which
                # PO/Part's progress+KPI count them) changes.
                cur.execute('UPDATE work_sessions SET operation_id=%s,quantity_confirmed=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *',(new_operation_id,session_id)); new=cur.fetchone()
                reconcile_operation_and_po(cur,int(source_op['id']))
                reconcile_operation_and_po(cur,int(target_op['id']))
                result=_json_safe({'old':dict(old),'item':dict(new),'reason':reason,
                    'from_operation':{'id':source_op['id'],'code':source_op['code'],'name':source_op['name']},
                    'to_operation':{'id':target_op['id'],'code':target_op['code'],'name':target_op['name']}})
                record_event(cur,event_type='OPERATION_TRANSFERRED',category='CHANGE',
                    title='Chuyển Operation cho Session',description=reason,
                    operation_id=new_operation_id,session_id=session_id,actor_id=user_id,actor_name=actor_name,
                    correlation_id=request_id,
                    metadata={'from_operation_id':source_op['id'],'from_operation_code':source_op['code'],
                              'to_operation_id':target_op['id'],'to_operation_code':target_op['code'],'reason':reason})
                if request_id:cur.execute('INSERT INTO kiosk_idempotency(request_id,action,response_json) VALUES(%s,%s,%s)',(request_id,'SESSION_OPERATION_TRANSFER',Jsonb(result)))
                return result

    def exclude_session(self,session_id,data,user_id,actor_username=''):
        """Loai khoi bao cao (spec section 7): never deletes -- the session
        stays in history/audit forever, only its contribution to time/
        quantity/KPI/progress reporting stops (reconcile_operation() filters
        excluded_from_reports=TRUE out at the source, see migration 0042)."""
        reason=str(data.get('reason') or '').strip()
        if not reason: raise ValueError('Phải chọn lý do khi loại Session khỏi báo cáo')
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if not pre: raise NotFoundError('session not found')
                lock_production_order_for_operation_first(cur,pre['operation_id'])
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); old=cur.fetchone()
                if not old: raise NotFoundError('session not found')
                if old['excluded_from_reports']: raise ConflictError('Session đã được loại khỏi báo cáo')
                cur.execute("""UPDATE work_sessions SET excluded_from_reports=TRUE,exclusion_reason=%s,
                    excluded_by=%s,excluded_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s RETURNING *""",(reason,actor_username,session_id)); new=cur.fetchone()
                reconcile_operation_and_po(cur,int(old['operation_id']))
                result=_json_safe({'old':dict(old),'item':dict(new),'reason':reason})
                record_event(cur,event_type='SESSION_EXCLUDED',category='CHANGE',title='Loại Session khỏi báo cáo',
                    description=reason,operation_id=old['operation_id'],session_id=session_id,actor_id=user_id,
                    actor_name=actor_username,metadata={'reason':reason})
                return result

    def restore_session(self,session_id,data,user_id,actor_username=''):
        """Undo exclude_session() -- report/KPI/progress count this session
        again from the next reconcile onward. Requires a reason for the same
        auditability reason exclude itself does."""
        reason=str(data.get('reason') or '').strip()
        if not reason: raise ValueError('Phải nhập lý do khôi phục Session vào báo cáo')
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT operation_id FROM work_sessions WHERE id=%s',(session_id,)); pre=cur.fetchone()
                if not pre: raise NotFoundError('session not found')
                lock_production_order_for_operation_first(cur,pre['operation_id'])
                cur.execute('SELECT * FROM work_sessions WHERE id=%s FOR UPDATE',(session_id,)); old=cur.fetchone()
                if not old: raise NotFoundError('session not found')
                if not old['excluded_from_reports']: raise ConflictError('Session hiện không bị loại khỏi báo cáo')
                cur.execute("""UPDATE work_sessions SET excluded_from_reports=FALSE,exclusion_reason='',
                    excluded_by='',excluded_at=NULL,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s RETURNING *""",(session_id,)); new=cur.fetchone()
                reconcile_operation_and_po(cur,int(old['operation_id']))
                result=_json_safe({'old':dict(old),'item':dict(new),'reason':reason})
                record_event(cur,event_type='SESSION_RESTORED',category='CHANGE',title='Khôi phục Session vào báo cáo',
                    description=reason,operation_id=old['operation_id'],session_id=session_id,actor_id=user_id,
                    actor_name=actor_username,metadata={'reason':reason,'previous_exclusion_reason':old.get('exclusion_reason')})
                return result

    def penalty(self,data,user_id):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO penalty_tickets(employee_id,operation_id,session_id,points,reason,issued_by)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",(int(data['employee_id']),data.get('operation_id'),data.get('session_id'),int(data.get('points',0) or 0),str(data.get('reason','')),user_id)); return cur.fetchone()
