import uuid
from flask import Blueprint,g,jsonify,request,session
from mesflow.web.auth import login_required,production_client_required,roles_required
from mesflow.db.repositories.base import NotFoundError,ConflictError,RepositoryError
from mesflow.db.repositories.execution import KioskRepository,WorkSessionRepository,QCRepository,SupervisorRepository,_json_safe
from mesflow.db.repositories.analytics import AuditRepository,KioskEventRepository
from mesflow.db.connection import transaction,fetch_one
from mesflow.db.repositories.production_state import reconcile_operation_and_po,reconcile_po_tree
from mesflow.db.repositories.offline_sync import OfflineSyncRepository
from mesflow.db.repositories.server_generation import ServerGenerationRepository
from mesflow.web.errors import api_error_response
from mesflow.services.session_service import SessionService,StartSessionCommand,FinishSessionCommand
bp=Blueprint('execution',__name__,url_prefix='/api')
_session_service=SessionService()

class KioskRepositoryLookup:
    @staticmethod
    def employee(qr,key):
        from mesflow.db.connection import fetch_one
        return fetch_one("SELECT id,employee_no,name,qr FROM employees WHERE active=TRUE AND (upper(qr)=upper(%s) OR upper(employee_no)=upper(%s)) LIMIT 1",(qr,key))
    @staticmethod
    def operation(qr,key):
        from mesflow.db.connection import fetch_one
        return fetch_one("SELECT o.id,o.code,o.name,o.qr,p.code part_code,po.code po_code,po.status po_status FROM operations o LEFT JOIN parts p ON p.id=o.part_id LEFT JOIN production_orders po ON po.id=o.production_order_id WHERE upper(o.qr)=upper(%s) OR upper(o.code)=upper(%s) LIMIT 1",(qr,key))
    @staticmethod
    def station(code):
        from mesflow.db.connection import fetch_one
        return fetch_one("SELECT id,code,name FROM stations WHERE upper(code)=upper(%s) LIMIT 1",(code,)) if code else None
def err(exc):
    return api_error_response(exc,logger_name=__name__)
@bp.get('/execution/health')
def health(): return jsonify(ok=True,backend='postgresql',phase='execution',modules=['kiosk','work-sessions','quantity','qc','supervisor'])
@bp.post('/kiosk/register')
def register():
    try: return jsonify(ok=True,identity=KioskRepository().register(request.get_json(silent=True) or {})),201
    except Exception as exc: return err(exc)
@bp.post('/kiosk-identities/<int:identity_id>/approve')
@roles_required('admin','manager')
def approve(identity_id):
    try:
        row,token=KioskRepository().approve(identity_id,int((request.get_json(silent=True) or {})['station_id']))
        AuditRepository().log(str(session.get('username','')),'KIOSK_APPROVE','kiosk_identity',str(identity_id),{'station_id':int((request.get_json(silent=True) or {})['station_id'])})
        return jsonify(ok=True,identity=row,token=token)
    except Exception as exc: return err(exc)
@bp.post('/kiosk/heartbeat')
def heartbeat():
    body=request.get_json(silent=True) or {}
    try:
        KioskRepository().verify_token(str(body.get('device_uuid','')),str(request.headers.get('X-Kiosk-Token','')))
        status=KioskRepository().heartbeat(str(body['device_uuid']),body)
        return jsonify(ok=True,status=status)
    except Exception as exc: return err(exc)
@bp.get('/work-sessions')
@login_required
def list_sessions(): return jsonify(ok=True,items=WorkSessionRepository().list())
@bp.post('/work-sessions/start')
@production_client_required
def start_session():
    # V66 flagship migration: Route -> Typed Command -> Service -> Domain
    # validation -> Repository -> single transaction -> Audit -> Domain
    # Event. Response shape is unchanged: {"ok":true,"session":{...},
    # "idempotent_replay":bool}, HTTP 201, same as before this migration.
    body=request.get_json(silent=True) or {}
    try:
        command=StartSessionCommand(
            employee_id=int(body.get('employee_id') or 0),operation_id=int(body.get('operation_id') or 0),
            request_id=str(body.get('request_id','')),station_id=int(body['station_id']) if body.get('station_id') else None,
            device_uuid=str(body.get('device_uuid','')),actor_username=str(session.get('username','')),
            actor_user_id=session.get('user_id'),correlation_id=str(getattr(g,'trace_id','') or ''))
        result=_session_service.start_session(command)
        return jsonify(ok=True,session=result.session,idempotent_replay=result.idempotent_replay),201
    except Exception as exc: return err(exc)
@bp.post('/work-sessions/<int:session_id>/finish')
@production_client_required
def finish_session(session_id):
    # V66 flagship migration (see start_session above). Response shape
    # unchanged: {"ok":true,"session":{...},"idempotent_replay":bool}, HTTP
    # 200, same as before this migration. The Kiosk-facing
    # /api/kiosk-web/finish/<id> route (mesflow.web.kiosk) is intentionally
    # left calling WorkSessionRepository directly -- device protocol is out
    # of scope for this migration.
    body=request.get_json(silent=True) or {}
    try:
        command=FinishSessionCommand(
            session_id=session_id,request_id=str(body.get('request_id','')),
            good_qty=max(int(body.get('good_qty',0) or 0),0),defect_qty=max(int(body.get('defect_qty',0) or 0),0),
            rework_qty=max(int(body.get('rework_qty',0) or 0),0),note=str(body.get('note','')),
            actor_username=str(session.get('username','')),actor_user_id=session.get('user_id'),
            correlation_id=str(getattr(g,'trace_id','') or ''))
        result=_session_service.finish_session(command)
        return jsonify(ok=True,session=result.session,idempotent_replay=result.idempotent_replay)
    except Exception as exc: return err(exc)
@bp.post('/production-state/reconcile')
@roles_required('admin','manager')
def reconcile_production_state():
    body=request.get_json(silent=True) or {}
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                if body.get('operation_id'):
                    result=reconcile_operation_and_po(cur,int(body['operation_id']))
                elif body.get('po_id'):
                    result=reconcile_po_tree(cur,int(body['po_id']))
                else:
                    raise ValueError('operation_id or po_id required')
        AuditRepository().log(str(session.get('username','')),'PRODUCTION_STATE_RECONCILE',
                              'operation' if body.get('operation_id') else 'production_order',
                              str(body.get('operation_id') or body.get('po_id')),{'result':result})
        return jsonify(ok=True,**result)
    except Exception as exc: return err(exc)
@bp.get('/qc/inspections')
@login_required
def list_qc(): return jsonify(ok=True,items=QCRepository().list())
@bp.post('/qc/inspections')
@roles_required('admin','manager','supervisor')
def start_qc():
    try:
        item=QCRepository().start(request.get_json(silent=True) or {},session.get('user_id'))
        AuditRepository().log(str(session.get('username','')),'QC_START','qc_inspection',str(item['id']))
        return jsonify(ok=True,item=item),201
    except Exception as exc: return err(exc)
@bp.post('/qc/inspections/<int:inspection_id>/complete')
@roles_required('admin','manager','supervisor')
def complete_qc(inspection_id):
    try:
        item=QCRepository().complete(inspection_id,request.get_json(silent=True) or {})
        AuditRepository().log(str(session.get('username','')),'QC_COMPLETE','qc_inspection',str(inspection_id))
        return jsonify(ok=True,item=item)
    except Exception as exc: return err(exc)
@bp.post('/supervisor/sessions/<int:session_id>/adjust')
@roles_required('admin','manager','supervisor')
def adjust(session_id):
    try:
        item=SupervisorRepository().adjust(session_id,request.get_json(silent=True) or {},session.get('user_id'))
        AuditRepository().log(str(session.get('username','')),'SESSION_ADJUST','work_session',str(session_id),request.get_json(silent=True) or {})
        return jsonify(ok=True,item=item)
    except Exception as exc: return err(exc)

@bp.patch('/supervisor/sessions/<int:session_id>')
@roles_required('admin','manager','supervisor')
def edit_session_full(session_id):
    try:
        body=request.get_json(silent=True) or {}
        result=SupervisorRepository().edit_session(session_id,body,session.get('user_id'))
        AuditRepository().log(str(session.get('username','')),'SESSION_EDIT','work_session',str(session_id),_json_safe({'reason':body.get('reason'),'old':result['old'],'new':result['item']}))
        return jsonify(ok=True,item=result['item'])
    except Exception as exc: return err(exc)

@bp.post('/supervisor/sessions/<int:session_id>/transfer-operation')
@roles_required('admin','manager','supervisor')
def transfer_session_operation(session_id):
    try:
        body=request.get_json(silent=True) or {}
        actor_role=str(session.get('role') or '')
        result=SupervisorRepository().transfer_operation(session_id,body,session.get('user_id'),actor_role=actor_role)
        AuditRepository().log(str(session.get('username','')),'SESSION_OPERATION_TRANSFER','work_session',str(session_id),
            _json_safe({'reason':body.get('reason'),'from_operation':result['from_operation'],'to_operation':result['to_operation']}))
        return jsonify(ok=True,item=result['item'])
    except Exception as exc: return err(exc)

@bp.post('/supervisor/sessions/<int:session_id>/exclude')
@roles_required('admin','manager','supervisor')
def exclude_session(session_id):
    try:
        body=request.get_json(silent=True) or {}
        actor_username=str(session.get('username') or '')
        result=SupervisorRepository().exclude_session(session_id,body,session.get('user_id'),actor_username=actor_username)
        AuditRepository().log(actor_username,'SESSION_EXCLUDE','work_session',str(session_id),_json_safe({'reason':body.get('reason')}))
        return jsonify(ok=True,item=result['item'])
    except Exception as exc: return err(exc)

@bp.post('/supervisor/sessions/<int:session_id>/restore')
@roles_required('admin','manager','supervisor')
def restore_session(session_id):
    try:
        body=request.get_json(silent=True) or {}
        actor_username=str(session.get('username') or '')
        result=SupervisorRepository().restore_session(session_id,body,session.get('user_id'),actor_username=actor_username)
        AuditRepository().log(actor_username,'SESSION_RESTORE','work_session',str(session_id),_json_safe({'reason':body.get('reason')}))
        return jsonify(ok=True,item=result['item'])
    except Exception as exc: return err(exc)

@bp.post('/supervisor/penalties')
@roles_required('admin','manager','supervisor')
def penalty():
    try: return jsonify(ok=True,item=SupervisorRepository().penalty(request.get_json(silent=True) or {},session.get('user_id'))),201
    except Exception as exc: return err(exc)



def _legacy_kiosk_identity(body=None):
    """Compatibility identity resolver for hardware kiosks.

    Kiosk tokens are still NOT required for legacy/ESP32 execution APIs
    (unchanged -- that's a separate, larger compatibility decision than
    this fix). Business validation (employee/operation/station/session)
    remains enforced by the endpoints, same as before.

    SECURITY BUG this used to have, found live: for an
    EXISTING identity, it silently flipped DISABLED/PENDING back to ACTIVE
    on every single request (an admin disabling a compromised/decommissioned
    kiosk via /kiosk-management/<id>/status did nothing -- the device's own
    next heartbeat undid it before the admin's next page load). Fixed: an
    existing DISABLED identity now REJECTS execution (403); PENDING also
    rejects (still awaiting an admin's explicit /approve). Only a
    genuinely-ACTIVE identity is allowed through, same as
    /kiosk-management's own status is meant to actually mean.

    Auto-bind-on-first-contact (an UNKNOWN device_uuid silently becoming a
    new ACTIVE identity, no admin approval) is now gated behind
    MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND, default OFF/production-safe. When
    OFF, an unrecognized device gets a clear 403 pointing at
    /kiosk-management (register+approve explicitly) instead of a silent
    auto-bind. When ON (an environment still relying on the old
    zero-touch-provisioning fleet behavior, opting in explicitly), the
    original auto-bind-as-ACTIVE behavior is unchanged -- this is a
    deliberate compatibility mode, not removed, so an existing ESP32 fleet
    is never silently broken by this change.
    """
    from mesflow.core.config import settings
    from mesflow.domain.errors import PermissionDeniedError
    body = body or {}
    candidates = [
        body.get('device_uuid'),
        request.headers.get('X-Device-UUID'),
        body.get('device_id'),
        request.headers.get('X-Device-ID'),
    ]
    device = next((str(x).strip() for x in candidates if str(x or '').strip()), '')
    if not device:
        device = 'LEGACY-' + str(request.remote_addr or 'UNKNOWN').replace(':','-')

    from mesflow.db.connection import fetch_one
    row = fetch_one("SELECT * FROM kiosk_identities WHERE device_uuid=%s LIMIT 1", (device,))
    if row:
        status = str(row.get('status') or '').upper()
        if status != 'ACTIVE':
            raise PermissionDeniedError(
                f"Kiosk '{device}' đang ở trạng thái {status} -- liên hệ quản trị viên để kích hoạt lại qua /kiosk-management."
            )
        return row

    if not settings.allow_legacy_kiosk_autobind:
        raise PermissionDeniedError(
            f"Kiosk '{device}' chưa được đăng ký. Đăng ký và duyệt qua /kiosk-management trước khi sử dụng."
        )

    import logging
    logging.getLogger(__name__).warning(
        'MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1: auto-binding unknown device_uuid=%s as ACTIVE with no admin approval', device)
    bind_body = dict(body)
    bind_body['device_uuid'] = device
    bind_body.setdefault('device_id', device)
    if not bind_body.get('station_code'):
        bind_body['station_code'] = str(body.get('station_id') or request.headers.get('X-Station-ID') or '')
    row, _token = KioskRepository().bind_legacy(bind_body, request.remote_addr or '')
    return row

@bp.post('/kiosk/bind')
@bp.post('/kiosk/connect')
def legacy_kiosk_bind():
    body=request.get_json(silent=True) or {}
    try:
        import hashlib,logging
        from mesflow.core.config import settings
        from mesflow.domain.errors import PermissionDeniedError
        device=str(body.get('device_uuid') or body.get('device_id') or '').strip()
        if not device:
            raise ValueError('device_id required')
        existing=fetch_one("SELECT status,token_hash FROM kiosk_identities WHERE device_uuid=%s LIMIT 1",(device,))
        if existing and str(existing.get('status') or '').upper()!='ACTIVE':
            raise PermissionDeniedError(
                f"Kiosk '{device}' đang ở trạng thái {existing.get('status')} -- chỉ quản trị viên mới có thể kích hoạt lại."
            )
        if not existing and not settings.allow_legacy_kiosk_autobind:
            raise PermissionDeniedError(
                f"Kiosk '{device}' chưa được đăng ký. Đăng ký và duyệt qua /kiosk-management trước khi sử dụng."
            )
        if existing:
            # An identity that is already ACTIVE must prove possession of
            # its CURRENT token before bind_legacy() is allowed to rotate a
            # new one -- otherwise anyone who merely knows/guesses a real
            # device_uuid (a public identifier, sent in the clear on every
            # request) could hijack a live kiosk's credentials. Token can
            # arrive either the normal way (X-Kiosk-Token header) or in the
            # body (`kiosk_token`) for firmware that only knows how to POST
            # JSON on this specific legacy endpoint.
            presented=str(request.headers.get('X-Kiosk-Token') or body.get('kiosk_token') or '').strip()
            token_ok=bool(presented) and hashlib.sha256(presented.encode()).hexdigest()==existing.get('token_hash')
            if not token_ok:
                if settings.allow_legacy_unauthenticated_rebind:
                    logging.getLogger(__name__).warning(
                        'MESFLOW_ALLOW_LEGACY_UNAUTHENTICATED_REBIND=1: rebinding ACTIVE device_uuid=%s with no proof of its current token', device)
                else:
                    raise PermissionDeniedError(
                        f"Kiosk '{device}' đã kích hoạt -- cần đúng kiosk token hiện tại để rebind/đổi trạm. "
                        "Nếu mất token, quản trị viên phải cấp lại qua /kiosk-management."
                    )
        row,token=KioskRepository().bind_legacy(body,request.remote_addr or '')
        station = KioskRepositoryLookup.station(str(body.get('station_code') or '')) if body.get('station_code') else None
        generation=ServerGenerationRepository().current()
        return jsonify(ok=True,kiosk_token=token,device_uuid=row['device_uuid'],device_id=str(body.get('device_id') or row['device_uuid']),device_name=row.get('device_name'),station_id=row.get('station_id'),station_code=(station or {}).get('code') if station else body.get('station_code'),enabled=row['status']=='ACTIVE',config_version=1,cluster_id=generation['cluster_id'],generation_id=generation['generation_id'])
    except Exception as exc: return err(exc)

@bp.post('/station/heartbeat')
def legacy_station_heartbeat():
    body=request.get_json(silent=True) or {}
    try:
        identity=_legacy_kiosk_identity(body)
        device=str(identity['device_uuid'])
        mapped={
          'ui_state':body.get('ui_state','UNKNOWN'),'health_state':'ERROR' if body.get('last_error') else 'OK',
          'queue_size':body.get('queue_size') or body.get('pending_events') or 0,'wifi_rssi':body.get('wifi_rssi'),
          'free_heap':body.get('free_heap'),'last_error':body.get('last_error') or '',
          'firmware_version':body.get('firmware_version') or body.get('app_version') or '',
          'firmware_build':body.get('firmware_build') or '', 'hardware_model':body.get('hardware_model') or '',
          'ota_capable':bool(body.get('ota_capable',False)),
          'boot_id':body.get('boot_id') or '',
          'uptime_seconds':body.get('uptime_seconds') or 0,
          'boot_reason':body.get('boot_reason') or ''}
        status=KioskRepository().heartbeat(device,mapped)
        # DR reconciliation trigger (audit section 6/8): every heartbeat carries
        # the CURRENT cluster/generation. The kiosk compares generation_id to
        # what it stored at last bind/reconcile; a mismatch means it is now
        # talking to a server that was restored/failed-over since its last
        # successful sync, and it must enter RECONCILING before trusting its
        # "everything up to my last ACK is durable" assumption again.
        generation=ServerGenerationRepository().current()
        return jsonify(ok=True,enabled=True,config_version=1,status=status,cluster_id=generation['cluster_id'],generation_id=generation['generation_id'])
    except Exception as exc: return err(exc)

@bp.post('/kiosk/reconcile')
def kiosk_reconcile():
    """DR reconciliation manifest compare -- audit section 7. Called by the
    kiosk only when it detects generation_id changed (see heartbeat/bind
    above). Body: {device_uuid|device_id, sequence_min, sequence_max,
    recent_event_ids:[...]}. Never mutates any business data -- read-only
    comparison, plus updating the calling kiosk's own last_generation_id
    bookkeeping (OfflineSyncRepository.reconcile). Actual replay of missing
    events goes back through the existing /api/station/events/sync, so all
    of that endpoint's idempotency guarantees still apply unchanged."""
    body=request.get_json(silent=True) or {}
    try:
        identity=_legacy_kiosk_identity(body)
        device=str(identity['device_uuid'])
        result=OfflineSyncRepository().reconcile(
            device,
            int(body.get('sequence_min') or 0),
            int(body.get('sequence_max') or 0),
            list(body.get('recent_event_ids') or []),
        )
        generation=ServerGenerationRepository().current()
        return jsonify(ok=True,cluster_id=generation['cluster_id'],generation_id=generation['generation_id'],**result)
    except Exception as exc: return err(exc)

@bp.post('/station/events/sync')
@bp.post('/kiosk/offline-sync')
def legacy_station_events_sync():
    body=request.get_json(silent=True) or {}
    try:
        identity=_legacy_kiosk_identity(body)
        device=str(identity['device_uuid'])
        items=body.get('events') or []
        if not isinstance(items,list) or len(items)>25: raise ValueError('events must be an array with at most 25 items')
        items=sorted(items,key=lambda item:int((item or {}).get('local_sequence') or (item or {}).get('device_sequence') or 0))
        repo=OfflineSyncRepository()
        results=[]
        for item in items:
            result=repo.process_event(device,identity.get('station_id'),dict(item or {}))
            # Keep event_id during the firmware compatibility window.
            result['event_id']=result.get('client_event_id') or str((item or {}).get('event_id') or '')
            results.append(result)
        return jsonify(ok=True,results=results)
    except Exception as exc: return err(exc)

@bp.get('/kiosk/offline-snapshot')
def kiosk_offline_snapshot():
    try:
        body={'device_id':request.headers.get('X-Device-ID','')}
        identity=_legacy_kiosk_identity(body)
        station=fetch_one("SELECT code FROM stations WHERE id=%s",(identity.get('station_id'),)) if identity.get('station_id') else None
        return jsonify(ok=True,**OfflineSyncRepository().snapshot(str(identity['device_uuid']),str((station or {}).get('code') or '')))
    except Exception as exc:return err(exc)

@bp.get('/kiosk-management/overview')
@roles_required('admin','manager')
def kiosk_management_overview():
    try:return jsonify(ok=True,**KioskRepository().management_overview())
    except Exception as exc:return err(exc)

@bp.get('/kiosk-management/<path:device_uuid>/events')
@roles_required('admin','manager')
def kiosk_management_events(device_uuid):
    try:return jsonify(ok=True,items=KioskRepository().events_for_device(device_uuid,int(request.args.get('limit',300))))
    except Exception as exc:return err(exc)

@bp.post('/kiosk-management/<int:identity_id>/status')
@roles_required('admin','manager')
def kiosk_management_status(identity_id):
    try:
        body=request.get_json(silent=True) or {}; row=KioskRepository().set_status(identity_id,body.get('status'),body.get('station_id'))
        AuditRepository().log(str(session.get('username','')),'KIOSK_STATUS_CHANGE','kiosk_identity',str(identity_id),body)
        return jsonify(ok=True,item=row)
    except Exception as exc:return err(exc)

@bp.get('/kiosk-management/generation')
@roles_required('admin','manager')
def kiosk_management_generation():
    try:return jsonify(ok=True,generation=ServerGenerationRepository().current())
    except Exception as exc:return err(exc)

@bp.post('/kiosk-management/generation/bump')
@roles_required('admin')
def kiosk_management_generation_bump():
    """Explicit DR marker -- audit section 6. Call this exactly once after
    a real failover/DB-restore event, never automatically/heuristically.
    Every bound kiosk's next heartbeat/bind will see the new generation_id
    and enter RECONCILING (see esp-kiosk/esp/mesflow_app.cpp). admin-only
    (tighter than the other kiosk-management routes' admin+manager) because
    this is a cluster-wide DR signal, not routine kiosk administration."""
    try:
        body=request.get_json(silent=True) or {}
        reason=str(body.get('reason') or '').strip()
        if not reason: raise ValueError('reason required -- record why this generation was bumped')
        generation=ServerGenerationRepository().bump(reason,str(session.get('username','')))
        AuditRepository().log(str(session.get('username','')),'SERVER_GENERATION_BUMP','server_generation','1',{'reason':reason,'generation_id':generation['generation_id']})
        return jsonify(ok=True,generation=generation)
    except Exception as exc:return err(exc)


@bp.get('/lookup')
def legacy_lookup():
    qr=str(request.args.get('qr') or '').strip(); device=str(request.headers.get('X-Device-ID') or '')
    try:
        if not qr: raise ValueError('qr required')
        if qr.upper().startswith('WF|EMP|'):
            key=qr.split('|')[-1]
            row=KioskRepositoryLookup.employee(qr,key)
            if not row: raise NotFoundError('employee not found')
            active=WorkSessionRepository().list_open_for_employee(row['id'])
            if device: KioskEventRepository().ingest({'event_uuid':f'{device}-SCAN-EMP-{uuid.uuid4()}','device_uuid':device,'event_type':'SCAN_EMPLOYEE','severity':'INFO','message':f"Quét nhân viên {row['employee_no']}",'employee_id':row['id'],'payload':{'qr':qr}})
            return jsonify(ok=True,type='worker',worker={'id':row['id'],'code':row['employee_no'],'employee_code':row['employee_no'],'name':row['name'],'qr':row['qr']},active_sessions=active)
        if qr.upper().startswith('WF|OP|'):
            key=qr.split('|')[-1]
            row=KioskRepositoryLookup.operation(qr,key)
            if not row: raise NotFoundError('operation not found')
            if device: KioskEventRepository().ingest({'event_uuid':f'{device}-SCAN-OP-{uuid.uuid4()}','device_uuid':device,'event_type':'SCAN_OPERATION','severity':'INFO','message':f"Quét OP {row['code']}",'operation_id':row['id'],'payload':{'qr':qr}})
            # BUG (found 2026-08-22): this is the endpoint the ESP32 kiosk actually
            # calls to validate an OP QR (/api/kiosk-web/scan's po_status check
            # never runs here). Without this, scanning an Operation whose PO has
            # already COMPLETED/CANCELLED or was never Started returned ok=True --
            # the kiosk let the worker proceed to enter quantity, and the real
            # rejection only surfaced (or didn't -- see esp.ino's offline-sync
            # "rejected" handling) once WorkSessionRepository.start() ran, deep in
            # the async offline-sync path, long after the worker had moved on.
            if str(row.get('po_status') or '').upper()!='IN_PROGRESS':
                raise ConflictError(f"PO {row.get('po_code') or ''} chưa Start hoặc đang tạm dừng")
            return jsonify(ok=True,type='operation',operation={'id':row['id'],'code':row['code'],'name':row['name'],'qr':row['qr'],'po':row['po_code'],'part':row['part_code']})
        raise ValueError('unsupported qr')
    except Exception as exc:return err(exc)

@bp.post('/session/group/start')
def legacy_group_start():
    body=request.get_json(silent=True) or {}
    try:
        # work_sessions.uq_open_session_per_employee (one
        # partial unique index, WHERE status='OPEN') means a SECOND start()
        # for the same employee within one "group" was ALWAYS guaranteed to
        # ConflictError -- start() commits its own transaction per call, so
        # this reliably left OP1 committed/OPEN and the whole API response
        # an error: a real partial-write bug.
        # Rather than build atomic multi-session START semantics the real
        # business rule doesn't actually support (an employee can only ever
        # have ONE open session -- confirmed at the schema level, not a
        # guess), reject a multi-operation group BEFORE creating anything.
        operation_qrs=list(body.get('operation_qrs') or [])
        if len(operation_qrs)>1:
            raise ConflictError(
                'Một nhân viên chỉ có thể có một Session đang mở -- không thể Start nhiều Operation cùng lúc cho một nhân viên. '
                'Hãy Start từng Operation một lượt.'
            )
        identity=_legacy_kiosk_identity(body)
        device=str(identity['device_uuid'])
        emp=KioskRepositoryLookup.employee(str(body.get('worker_qr') or ''),str(body.get('worker_qr') or '').split('|')[-1])
        if not emp: raise NotFoundError('employee not found')
        station=KioskRepositoryLookup.station(str(body.get('station_id') or request.headers.get('X-Station-ID') or ''))
        ids=[]; group=str(body.get('batch_token') or f'GROUP-{uuid.uuid4()}')
        for idx,oqr in enumerate(operation_qrs):
            op=KioskRepositoryLookup.operation(str(oqr),str(oqr).split('|')[-1])
            if not op: raise NotFoundError('operation not found')
            out=WorkSessionRepository().start({'request_id':group if idx==0 else f'{group}-{idx}','employee_id':emp['id'],'operation_id':op['id'],'station_id':station['id'] if station else None,'device_uuid':device})
            ids.append(out['session']['id'])
            KioskEventRepository().ingest({'event_uuid':f'{group}-{idx}-START','device_uuid':device or 'LEGACY','station_id':station['id'] if station else None,'event_type':'SESSION_START','severity':'INFO','message':f"Bắt đầu session OP {op['code']}",'session_id':out['session']['id'],'operation_id':op['id'],'employee_id':emp['id'],'payload':body})
        return jsonify(ok=True,group_id=group,session_ids=ids)
    except Exception as exc:return err(exc)

@bp.post('/session/group/finish')
def legacy_group_finish():
    body=request.get_json(silent=True) or {}
    try:
        identity=_legacy_kiosk_identity(body)
        device=str(identity['device_uuid'])
        station=KioskRepositoryLookup.station(str(body.get('station_id') or request.headers.get('X-Station-ID') or ''))
        results=list(body.get('results') or [])
        token=str(body.get('finish_token') or f'FINISH-{uuid.uuid4()}')
        # Atomic: finish_many() drives every item under
        # ONE shared transaction (execution.py), so this either fully
        # succeeds or fully rolls back, never a partial batch.
        items=[(int(item['session_id']),{'request_id':token if idx==0 else f'{token}-{idx}','good_qty':item.get('good_qty',0),'defect_qty':item.get('defect_qty',0),'rework_qty':item.get('rework_qty',0),'note':item.get('note','')})
               for idx,item in enumerate(results)]
        outs=WorkSessionRepository().finish_many(items)
        finished=[]
        for idx,(item,out) in enumerate(zip(results,outs)):
            sess=out['session']
            sid=int(item['session_id']); finished.append(sid)
            KioskEventRepository().ingest({'event_uuid':f'{token}-{idx}-FINISH','device_uuid':device or 'LEGACY','station_id':station['id'] if station else sess.get('station_id'),'event_type':'QUANTITY_REPORTED','severity':'ERROR' if int(item.get('defect_qty') or 0)>0 else 'INFO','message':f"Nhập SL đạt {item.get('good_qty',0)}, lỗi {item.get('defect_qty',0)}, sửa được {item.get('rework_qty',0)}",'session_id':sid,'operation_id':sess.get('operation_id'),'employee_id':sess.get('employee_id'),'payload':body})
        return jsonify(ok=True,group_id=body.get('session_group_id'),finished_session_ids=finished)
    except Exception as exc:return err(exc)
