from flask import Blueprint,jsonify,request,session
from mesflow.web.auth import login_required,roles_required
from mesflow.core.config import settings
from mesflow.db.repositories.base import NotFoundError,ConflictError,RepositoryError
from mesflow.db.repositories.analytics import AuditRepository,DashboardRepository,ReportRepository,KPIRepository,KioskEventRepository,NotificationRepository
from mesflow.core.working_calendar import get_working_calendar, get_work_shifts
from mesflow.db.connection import transaction
from psycopg.types.json import Jsonb
from mesflow.web.errors import api_error_response

bp=Blueprint('analytics',__name__,url_prefix='/api')

def error(exc):
    return api_error_response(exc,logger_name=__name__)

def actor(): return str(session.get('username') or 'system')

@bp.get('/analytics/health')
def health():
    try:
        summary=DashboardRepository().summary()
        return jsonify(ok=True,backend='postgresql',phase='analytics-events',summary=summary,modules=['dashboard','reports','kpi','audit','kiosk-events','notifications'])
    except Exception as exc: return error(exc)



@bp.get('/settings/work-shifts')
@login_required
def list_work_shifts_setting():
    try: return jsonify(ok=True,items=get_work_shifts(active_only=False))
    except Exception as exc: return error(exc)

@bp.put('/settings/work-shifts')
@roles_required('admin','manager')
def replace_work_shifts_setting():
    try:
        role=str(session.get('role') or '').lower()
        if role not in ('admin','manager'): return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền cấu hình ca'),403
        body=request.get_json(silent=True) or {}; items=body.get('items') or []
        if not items: raise ValueError('Phải có ít nhất một ca làm việc')
        normalized=[]; codes=set()
        for pos,item in enumerate(items):
            code=str(item.get('code') or '').strip().upper(); name=str(item.get('name') or '').strip()
            if not code or not name: raise ValueError('Mỗi ca phải có mã và tên')
            if code in codes: raise ValueError(f'Trùng mã ca {code}')
            codes.add(code); intervals=item.get('intervals') or []
            if not intervals: raise ValueError(f'Ca {code} chưa có khoảng thời gian')
            cleaned=[]; work_minutes=0; previous=-1
            for idx,iv in enumerate(sorted(intervals,key=lambda x:int(x.get('sort_order',0)))):
                typ=str(iv.get('interval_type') or '').upper(); a=int(iv.get('start_minute')); b=int(iv.get('end_minute'))
                if typ not in ('WORK','BREAK') or a<0 or b<=a or b>2880: raise ValueError(f'Khoảng thời gian không hợp lệ trong ca {code}')
                if a<previous: raise ValueError(f'Các khoảng của ca {code} bị chồng lấp')
                previous=b
                if typ=='WORK': work_minutes+=b-a
                cleaned.append({'interval_type':typ,'start_minute':a,'end_minute':b,'label':str(iv.get('label') or ''),'sort_order':idx*10+10})
            if work_minutes<=0: raise ValueError(f'Ca {code} phải có thời gian làm việc')
            normalized.append({'code':code,'name':name,'timezone':str(item.get('timezone') or settings.timezone_name),'anchor_start':str(item.get('anchor_start') or '08:00')[:5],
              'anchor_end':str(item.get('anchor_end') or '17:00')[:5],'cross_midnight':bool(item.get('cross_midnight')),
              'target_minutes':int(item.get('target_minutes') or work_minutes),'working_weekdays':[int(x) for x in item.get('working_weekdays',[0,1,2,3,4,5])],
              'sort_order':pos*10+10,'active':bool(item.get('active',True)),'intervals':cleaned})
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM work_shift_intervals')
                cur.execute('DELETE FROM work_shifts')
                for item in normalized:
                    cur.execute("""INSERT INTO work_shifts(code,name,timezone,anchor_start,anchor_end,cross_midnight,target_minutes,working_weekdays,sort_order,active)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(item['code'],item['name'],item['timezone'],item['anchor_start'],item['anchor_end'],item['cross_midnight'],item['target_minutes'],item['working_weekdays'],item['sort_order'],item['active']))
                    shift_id=cur.fetchone()['id']
                    for iv in item['intervals']:
                        cur.execute("""INSERT INTO work_shift_intervals(shift_id,interval_type,start_minute,end_minute,label,sort_order)
                          VALUES(%s,%s,%s,%s,%s,%s)""",(shift_id,iv['interval_type'],iv['start_minute'],iv['end_minute'],iv['label'],iv['sort_order']))
        AuditRepository().log(actor(),'WORK_SHIFTS_REPLACE','work_shift','all',{'items':normalized})
        return jsonify(ok=True,items=get_work_shifts(active_only=False))
    except Exception as exc: return error(exc)

@bp.get('/settings/working-calendar')
@login_required
def get_working_calendar_setting():
    try: return jsonify(ok=True,item=get_working_calendar(),shifts=get_work_shifts())
    except Exception as exc: return error(exc)

@bp.patch('/settings/working-calendar')
@roles_required('admin','manager')
def update_working_calendar_setting():
    return jsonify(ok=False,error='MOVED',message='Lịch làm việc đã chuyển sang cấu hình nhiều ca tại /api/settings/work-shifts'),409

@bp.get('/dashboard/overview')
@login_required
def dashboard_overview():
    try: return jsonify(ok=True,**DashboardRepository().overview(int(request.args.get('limit',2000))))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/control-tower')
@login_required
def dashboard_control_tower():
    try: return jsonify(ok=True,**DashboardRepository().control_tower(int(request.args.get('limit',100))))
    except Exception as exc: return error(exc)


@bp.get('/production-schedule')
@login_required
def production_schedule():
    try: return jsonify(ok=True,items=DashboardRepository().production_schedule(int(request.args.get('limit',200))))
    except Exception as exc: return error(exc)

@bp.get('/production-control')
@login_required
def production_control():
    try: return jsonify(ok=True,**DashboardRepository().production_control(int(request.args.get('limit',2000))))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/summary')
@login_required
def dashboard_summary():
    try: return jsonify(ok=True,summary=DashboardRepository().summary())
    except Exception as exc: return error(exc)

@bp.get('/dashboard/production-orders')
@login_required
def dashboard_pos():
    try: return jsonify(ok=True,items=DashboardRepository().po_progress(int(request.args.get('limit',100))))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/active-sessions')
@login_required
def dashboard_sessions():
    try: return jsonify(ok=True,items=DashboardRepository().active_sessions(int(request.args.get('limit',100))))
    except Exception as exc: return error(exc)


@bp.get('/dashboard/daily-progress')
@login_required
def dashboard_daily_progress():
    try:
        shift_id=int(request.args.get('shift_id')) if request.args.get('shift_id','').strip() else None
        return jsonify(ok=True,items=DashboardRepository().daily_progress(request.args.get('shift_date') or request.args.get('date'),int(request.args.get('limit',500)),shift_id,request.args.get('shift')))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/daily-sessions')
@login_required
def dashboard_daily_sessions():
    try:
        shift_id=int(request.args.get('shift_id')) if request.args.get('shift_id','').strip() else None
        return jsonify(ok=True,items=DashboardRepository().daily_sessions(request.args.get('shift_date') or request.args.get('date'),int(request.args.get('limit',1000)),shift_id,request.args.get('shift')))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/shift')
@login_required
def dashboard_shift():
    try:
        shift_id=int(request.args.get('shift_id')) if request.args.get('shift_id','').strip() else None
        if shift_id is None: raise ValueError('Thiếu shift_id')
        return jsonify(ok=True,**DashboardRepository().shift_dashboard(request.args.get('shift_date'),shift_id,int(request.args.get('limit',1000))))
    except Exception as exc: return error(exc)

@bp.get('/dashboard/recent-activity')
@login_required
def dashboard_activity():
    try: return jsonify(ok=True,items=DashboardRepository().recent_activity(int(request.args.get('limit',100))))
    except Exception as exc: return error(exc)

@bp.get('/reports/production-orders/<int:po_id>')
@login_required
def po_report(po_id):
    try: return jsonify(ok=True,report=ReportRepository().production_order(po_id))
    except Exception as exc: return error(exc)

@bp.get('/reports/operations/<int:operation_id>')
@login_required
def operation_report(operation_id):
    try: return jsonify(ok=True,report=ReportRepository().operation(operation_id))
    except Exception as exc: return error(exc)



@bp.get('/session-management/operations')
@login_required
def session_management_operations():
    try:
        role=str(session.get('role') or '').lower()
        if role not in ('admin','manager','supervisor'):
            return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền quản lý session'),403
        value=lambda name: int(request.args[name]) if request.args.get(name,'').strip() else None
        report=ReportRepository().recent_session_operations(value('po_id'),value('part_id'),value('operation_id'),value('employee_id'),request.args.get('activity','recent'),int(request.args.get('limit',50)))
        return jsonify(ok=True,**report)
    except Exception as exc: return error(exc)

@bp.get('/session-management')
@login_required
def session_management():
    try:
        role=str(session.get('role') or '').lower()
        if role not in ('admin','manager','supervisor'):
            return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền quản lý session'),403
        value=lambda name: int(request.args[name]) if request.args.get(name,'').strip() else None
        report=ReportRepository().session_management(value('po_id'),value('part_id'),value('operation_id'),value('employee_id'),request.args.get('status'),request.args.get('from'),request.args.get('to'),int(request.args.get('limit',3000)))
        return jsonify(ok=True,**report)
    except Exception as exc: return error(exc)

@bp.get('/session-exceptions')
@login_required
def session_exceptions():
    try:
        role=str(session.get('role') or '').lower()
        if role not in ('admin','manager','supervisor'):
            return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền xem session bất thường'),403
        employee_id=int(request.args['employee_id']) if request.args.get('employee_id','').strip() else None
        return jsonify(ok=True,items=ReportRepository().session_exceptions(
            request.args.get('status'),employee_id,int(request.args.get('limit',1000)),request.args.get('workflow_status')))
    except Exception as exc: return error(exc)

@bp.patch('/session-exceptions/workflow')
@roles_required('admin','manager','supervisor')
def update_session_exception_workflow():
    try:
        role=str(session.get('role') or '').lower()
        if role not in ('admin','manager','supervisor'):
            return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền xử lý session bất thường'),403
        body=request.get_json(silent=True) or {}
        rows=ReportRepository().update_session_exception_reviews(
            body.get('items') or [],body.get('workflow_status'),str(body.get('note') or '').strip(),
            actor(),str(body.get('assigned_to') or '').strip(),str(body.get('resolution') or '').strip())
        AuditRepository().log(actor(),'SESSION_EXCEPTION_WORKFLOW_UPDATE','session_exception','bulk',{
            'workflow_status':body.get('workflow_status'),'note':body.get('note'),'assigned_to':body.get('assigned_to'),
            'resolution':body.get('resolution'),'items':body.get('items') or []})
        return jsonify(ok=True,items=rows,updated_count=len(rows))
    except Exception as exc: return error(exc)

@bp.get('/reports/operation-sessions')
@login_required
def operation_sessions_report():
    try:
        op=request.args.get('operation_id','').strip()
        employee=request.args.get('employee_id','').strip()
        report=ReportRepository().operation_sessions(
            int(op) if op else None,request.args.get('from'),request.args.get('to'),
            int(employee) if employee else None,request.args.get('status'),int(request.args.get('limit',3000)))
        return jsonify(ok=True,report=report)
    except Exception as exc: return error(exc)

@bp.get('/reports/employee-performance')
@login_required
def employee_performance_report():
    try:
        employee=request.args.get('employee_id','').strip()
        report=ReportRepository().employee_performance(
            int(employee) if employee else None,request.args.get('from'),request.args.get('to'),
            request.args.get('status'),int(request.args.get('limit',10000)))
        return jsonify(ok=True,report=report)
    except Exception as exc: return error(exc)

@bp.get('/kpi/employees')
@login_required
def employee_kpi():
    try: return jsonify(ok=True,items=KPIRepository().employees(request.args.get('from'),request.args.get('to'),int(request.args.get('limit',500))))
    except Exception as exc: return error(exc)

@bp.get('/kpi/operations')
@login_required
def operation_kpi():
    try: return jsonify(ok=True,items=KPIRepository().operations(int(request.args.get('limit',500))))
    except Exception as exc: return error(exc)

@bp.post('/kpi/snapshots')
@roles_required('admin','manager')
def snapshot_kpi():
    try:
        row=KPIRepository().snapshot()
        AuditRepository().log(actor(),'KPI_SNAPSHOT','kpi_snapshot',str(row['id']),{'snapshot_date':str(row['snapshot_date'])})
        return jsonify(ok=True,item=row),201
    except Exception as exc: return error(exc)

@bp.get('/audit-logs')
@login_required
def audit_logs():
    try: return jsonify(ok=True,items=AuditRepository().list(int(request.args.get('limit',200)),request.args.get('action',''),request.args.get('entity_type','')))
    except Exception as exc: return error(exc)

@bp.post('/kiosk/events')
def kiosk_event_ingest():
    try: return jsonify(ok=True,event=KioskEventRepository().ingest(request.get_json(silent=True) or {})),201
    except Exception as exc: return error(exc)

@bp.get('/kiosk/events')
@login_required
def kiosk_events():
    try: return jsonify(ok=True,items=KioskEventRepository().list(int(request.args.get('limit',200)),request.args.get('status',''),request.args.get('severity',''),request.args.get('device_uuid',''),request.args.get('event_type','')))
    except Exception as exc: return error(exc)

@bp.post('/kiosk/events/<int:event_id>/resolve')
@roles_required('admin','manager','supervisor')
def resolve_kiosk_event(event_id):
    try:
        body=request.get_json(silent=True) or {}
        row=KioskEventRepository().resolve(event_id,int(session['user_id']),str(body.get('note','')))
        AuditRepository().log(actor(),'KIOSK_EVENT_RESOLVE','kiosk_event',str(event_id),{'note':body.get('note','')})
        return jsonify(ok=True,event=row)
    except Exception as exc: return error(exc)

@bp.get('/notifications')
@login_required
def notifications():
    try: return jsonify(ok=True,items=NotificationRepository().list(int(request.args.get('limit',200)),request.args.get('status',''),str(session.get('role',''))))
    except Exception as exc: return error(exc)

@bp.post('/notifications/<int:notification_id>/read')
@login_required
def notification_read(notification_id):
    try: return jsonify(ok=True,item=NotificationRepository().mark_read(notification_id,int(session['user_id'])))
    except Exception as exc: return error(exc)
