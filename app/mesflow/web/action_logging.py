import json, logging, time, traceback, uuid
from flask import Blueprint, g, jsonify, request, session
from werkzeug.exceptions import HTTPException
from mesflow.core.config import settings
from mesflow.db.connection import transaction, fetch_all, fetch_one
from mesflow.web.auth import admin_required
from mesflow.core.log_retention import preview as retention_preview, run as retention_run
logger=logging.getLogger('mesflow.action_log')
bp=Blueprint('action_logging',__name__,url_prefix='/api/system')
SENSITIVE=('password','token','authorization','cookie','secret','api_key')
SCANNER_MARKERS=(
    '/vendor/phpunit/', '/phpunit/', '/eval-stdin.php', '/index.php', '/public/index.php',
    '/wp-admin', '/wp-login.php', '/xmlrpc.php', '/.env', '/.git/', '/config.php',
    '/shell.php', '/adminer.php', '/phpmyadmin', '/cgi-bin/', '/boaform/'
)
def _is_scanner_noise(path):
    p=(path or '').lower()
    return any(marker in p for marker in SCANNER_MARKERS) or p.endswith(('.php','.asp','.aspx','.jsp','.cgi'))
def _clean(value,depth=0):
    if depth>6:return '<max-depth>'
    if isinstance(value,dict):return {str(k):('***' if any(x in str(k).lower() for x in SENSITIVE) else _clean(v,depth+1)) for k,v in value.items()}
    if isinstance(value,list):return [_clean(v,depth+1) for v in value[:100]]
    if isinstance(value,str):return value[:4000]
    if isinstance(value,(int,float,bool)) or value is None:return value
    return str(value)[:1000]
def _json(value):
    try:return json.dumps(_clean(value),ensure_ascii=False,default=str)[:settings.action_log_body_limit]
    except Exception:return '{}'
def _source():
    device=request.headers.get('X-Device-ID') or request.headers.get('X-Kiosk-ID') or ''
    station=request.headers.get('X-Station-ID') or request.headers.get('X-Station-Code') or ''
    return ('KIOSK',device,station) if device or request.path.startswith(('/api/station/','/api/kiosk/')) else ('WEB','','')
def _payload():
    if request.is_json:return request.get_json(silent=True) or {}
    if request.form:return request.form.to_dict(flat=True)
    return {'args':request.args.to_dict(flat=True)} if request.args else {}
def begin_request():
    if settings.action_log_enabled:
        g.action_started=time.perf_counter();g.trace_id=request.headers.get('X-Trace-ID') or str(uuid.uuid4());g.action_exception=None
def capture_exception(exc):g.action_exception=exc
def finish_request(response):
    if not settings.action_log_enabled or not getattr(g,'trace_id',None):return response
    response.headers['X-Trace-ID']=g.trace_id
    duration=int((time.perf_counter()-getattr(g,'action_started',time.perf_counter()))*1000);status=int(response.status_code);exc=getattr(g,'action_exception',None)
    if request.method in {'GET','HEAD','OPTIONS'} and not settings.action_log_get_requests and status<400 and duration<settings.action_log_slow_ms:return response
    if status==404 and _is_scanner_noise(request.path) and not settings.action_log_scanner_noise:return response
    source,device,station=_source();outcome='ERROR' if status>=500 or exc else ('FAILED' if status>=400 else ('SLOW' if duration>=settings.action_log_slow_ms else 'SUCCESS'))
    try: response_data=response.get_json(silent=True) if response.is_json else {}
    except Exception: response_data={}
    error_type=type(exc).__name__ if exc else (str((response_data or {}).get('error','')) if status>=400 else '')
    error_message=str(exc) if exc else (str((response_data or {}).get('message') or (response_data or {}).get('error') or '') if status>=400 else '')
    tb=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__)) if exc else ''
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO action_logs(trace_id,parent_trace_id,actor_user_id,actor_username,actor_role,source_type,device_uuid,station_code,method,path,endpoint,action_name,http_status,duration_ms,outcome,error_type,error_message,request_json,response_json,context_json,traceback_text,client_ip,user_agent) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(g.trace_id,request.headers.get('X-Parent-Trace-ID'),session.get('user_id'),session.get('username',''),session.get('role',''),source,device,station,request.method,request.path,request.endpoint or '',request.headers.get('X-Action-Name') or request.endpoint or request.path,status,duration,outcome,error_type,error_message[:4000],_json(_payload()),_json(response_data or {}),_json({'query':request.args.to_dict(flat=True),'referer':request.headers.get('Referer','')[-1000:]}),tb[:30000],request.headers.get('X-Forwarded-For',request.remote_addr or '').split(',')[0].strip(),request.user_agent.string[:1000]))
                action_log_id=cur.fetchone()['id']
                if status>=500 or exc:
                    cur.execute("""INSERT INTO error_traces(trace_id,action_log_id,severity,error_type,error_message,traceback_text,path) VALUES(%s,%s,%s,%s,%s,%s,%s)""",(g.trace_id,action_log_id,'CRITICAL' if status>=500 else 'ERROR',error_type,error_message[:4000],tb[:30000],request.path))
    except Exception:logger.exception('Unable to persist action log trace_id=%s',g.trace_id)
    return response
def unhandled_error(exc):
    if isinstance(exc,HTTPException):
        status=int(exc.code or 500)
        error={404:'NOT_FOUND',405:'METHOD_NOT_ALLOWED',400:'BAD_REQUEST',401:'UNAUTHORIZED',403:'FORBIDDEN'}.get(status,'HTTP_ERROR')
        message='Đường dẫn không tồn tại.' if status==404 else str(exc.description or exc.name)
        return jsonify(ok=False,error=error,message=message,trace_id=getattr(g,'trace_id','')),status
    capture_exception(exc);logger.exception('Unhandled request error trace_id=%s path=%s',getattr(g,'trace_id',''),request.path)
    return jsonify(ok=False,error='INTERNAL_ERROR',message='Hệ thống gặp lỗi. Cung cấp trace_id cho bộ phận hỗ trợ.',trace_id=getattr(g,'trace_id','')),500
@bp.get('/action-logs')
@admin_required
def list_logs():
    limit=min(max(int(request.args.get('limit',300)),1),3000);where=[];params=[]
    if request.args.get('include_noise')!='1':where.append("NOT (http_status=404 AND (path ILIKE '%%.php%%' OR path ILIKE '%%/vendor/phpunit/%%' OR path ILIKE '%%/.env%%' OR path ILIKE '%%/.git/%%'))")
    for col,arg in [('outcome','outcome'),('actor_username','actor'),('source_type','source'),('device_uuid','device_uuid'),('station_code','station_code')]:
        val=request.args.get(arg,'').strip()
        if val:where.append(f'{col}=%s');params.append(val)
    q=request.args.get('q','').strip()
    if q:where.append('(trace_id ILIKE %s OR path ILIKE %s OR action_name ILIKE %s OR error_message ILIKE %s OR actor_username ILIKE %s OR device_uuid ILIKE %s)');params.extend([f'%{q}%']*6)
    if request.args.get('errors_only')=='1':where.append("outcome IN ('ERROR','FAILED')")
    clause=' WHERE '+' AND '.join(where) if where else ''
    rows=fetch_all(f"SELECT id,trace_id,actor_username,actor_role,source_type,device_uuid,station_code,method,path,endpoint,action_name,http_status,duration_ms,outcome,error_type,error_message,resolved,resolved_note,created_at FROM action_logs{clause} ORDER BY id DESC LIMIT %s",(*params,limit))
    return jsonify(ok=True,items=rows)
@bp.get('/action-logs/stats')
@admin_required
def stats():
    noise="NOT (http_status=404 AND (path ILIKE '%.php%' OR path ILIKE '%/vendor/phpunit/%' OR path ILIKE '%/.env%' OR path ILIKE '%/.git/%'))"
    row=fetch_one(f"SELECT COUNT(*) FILTER(WHERE created_at>=now()-interval '24 hours' AND {noise}) total_24h,COUNT(*) FILTER(WHERE created_at>=now()-interval '24 hours' AND outcome IN ('ERROR','FAILED') AND {noise}) errors_24h,COUNT(*) FILTER(WHERE created_at>=now()-interval '24 hours' AND outcome='SLOW' AND {noise}) slow_24h,COUNT(*) FILTER(WHERE outcome IN ('ERROR','FAILED') AND NOT resolved AND {noise}) unresolved,COALESCE(ROUND(AVG(duration_ms) FILTER(WHERE created_at>=now()-interval '24 hours' AND {noise})),0) avg_ms FROM action_logs")
    return jsonify(ok=True,summary=row)
@bp.get('/action-logs/<int:log_id>')
@admin_required
def detail(log_id):
    row=fetch_one('SELECT * FROM action_logs WHERE id=%s',(log_id,));return jsonify(ok=True,item=row) if row else (jsonify(ok=False,error='NOT_FOUND'),404)
@bp.post('/action-logs/<int:log_id>/resolve')
@admin_required
def resolve(log_id):
    note=str((request.get_json(silent=True) or {}).get('note','')).strip()
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE action_logs SET resolved=true,resolved_by_user_id=%s,resolved_note=%s,resolved_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING id',(session.get('user_id'),note,log_id))
            if not cur.fetchone():return jsonify(ok=False,error='NOT_FOUND'),404
    return jsonify(ok=True)


@bp.get('/error-traces')
@admin_required
def list_error_traces():
    limit=min(max(int(request.args.get('limit',300)),1),3000);where=[];params=[]
    status=request.args.get('status','').strip().upper()
    if status=='RESOLVED': where.append('e.resolved=true')
    elif status=='UNRESOLVED': where.append('e.resolved=false')
    severity=request.args.get('severity','').strip().upper()
    if severity: where.append('e.severity=%s');params.append(severity)
    q=request.args.get('q','').strip()
    if q:
        where.append('(e.trace_id ILIKE %s OR e.error_type ILIKE %s OR e.error_message ILIKE %s OR e.path ILIKE %s)')
        params.extend([f'%{q}%']*4)
    clause=' WHERE '+' AND '.join(where) if where else ''
    sql=("SELECT e.id,e.trace_id,e.action_log_id,e.severity,e.error_type,e.error_message,e.path,e.resolved,e.resolved_note,e.resolved_at,e.created_at,"
         "a.method,a.http_status,a.actor_username,a.source_type,a.device_uuid,a.station_code "
         "FROM error_traces e LEFT JOIN action_logs a ON a.id=e.action_log_id"+clause+" ORDER BY e.id DESC LIMIT %s")
    return jsonify(ok=True,items=fetch_all(sql,(*params,limit)))

@bp.get('/error-traces/stats')
@admin_required
def error_trace_stats():
    row=fetch_one("SELECT COUNT(*) FILTER(WHERE created_at>=now()-interval '24 hours') total_24h,COUNT(*) FILTER(WHERE NOT resolved) unresolved,COUNT(*) FILTER(WHERE severity='CRITICAL' AND NOT resolved) critical_unresolved,COUNT(*) FILTER(WHERE resolved AND resolved_at>=now()-interval '24 hours') resolved_24h FROM error_traces")
    return jsonify(ok=True,summary=row)

@bp.get('/error-traces/<int:trace_row_id>')
@admin_required
def error_trace_detail(trace_row_id):
    row=fetch_one("SELECT e.*,a.method,a.http_status,a.duration_ms,a.actor_username,a.actor_role,a.source_type,a.device_uuid,a.station_code,a.endpoint,a.request_json,a.response_json,a.context_json FROM error_traces e LEFT JOIN action_logs a ON a.id=e.action_log_id WHERE e.id=%s",(trace_row_id,))
    return jsonify(ok=True,item=row) if row else (jsonify(ok=False,error='NOT_FOUND'),404)

@bp.post('/error-traces/<int:trace_row_id>/resolve')
@admin_required
def resolve_error_trace(trace_row_id):
    payload=request.get_json(silent=True) or {};resolved=bool(payload.get('resolved',True));note=str(payload.get('note','')).strip()
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE error_traces SET resolved=%s,resolved_by_user_id=CASE WHEN %s THEN %s ELSE NULL END,resolved_note=%s,resolved_at=CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=%s RETURNING action_log_id",(resolved,resolved,session.get('user_id'),note,resolved,trace_row_id))
            row=cur.fetchone()
            if not row:return jsonify(ok=False,error='NOT_FOUND'),404
            if row.get('action_log_id'):
                cur.execute("UPDATE action_logs SET resolved=%s,resolved_by_user_id=CASE WHEN %s THEN %s ELSE NULL END,resolved_note=%s,resolved_at=CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=%s",(resolved,resolved,session.get('user_id'),note,resolved,row['action_log_id']))
    return jsonify(ok=True)

@bp.get('/log-retention/runs')
@admin_required
def list_log_retention_runs():
    limit=min(max(int(request.args.get('limit',100)),1),1000)
    return jsonify(ok=True,items=fetch_all('SELECT id,dry_run,action_deleted,error_deleted,details_json,started_at,finished_at FROM log_retention_runs ORDER BY id DESC LIMIT %s',(limit,)))

@bp.get('/log-retention/preview')
@admin_required
def log_retention_preview():
    return jsonify(ok=True,enabled=settings.log_retention_enabled,policy={
        'success_days':settings.log_retention_success_days,'slow_days':settings.log_retention_slow_days,
        'resolved_error_days':settings.log_retention_resolved_error_days,'unresolved_error_days':settings.log_retention_unresolved_error_days,
        'security_days':settings.log_retention_security_days,'error_trace_resolved_days':settings.log_retention_error_resolved_days,
        'error_trace_unresolved_days':settings.log_retention_error_unresolved_days,'batch_size':settings.log_retention_batch_size},preview=retention_preview())

@bp.post('/log-retention/run')
@admin_required
def log_retention_run():
    payload=request.get_json(silent=True) or {};dry_run=bool(payload.get('dry_run',False))
    if not settings.log_retention_enabled and not dry_run:return jsonify(ok=False,error='RETENTION_DISABLED'),409
    result=retention_run(dry_run=dry_run)
    return jsonify(ok=True,result=result)
