"""V67 Exception Center HTTP adapter; business transitions stay in services."""
from flask import Blueprint,g,jsonify,request,session
from mesflow.db.repositories.analytics import AuditRepository,ReportRepository
from mesflow.db.repositories.base import ConflictError,SessionChangedError
from mesflow.db.repositories.exceptions import ExceptionRepository
from mesflow.db.repositories.execution import SupervisorRepository,_json_safe
from mesflow.services.exception_service import ExceptionDecisionCommand,ExceptionDetectionService,ExceptionService
from mesflow.web.auth import login_required,roles_required
from mesflow.web.errors import api_error_response

bp=Blueprint('exceptions',__name__,url_prefix='/api')

def _allowed(): return str(session.get('role') or '').lower() in ('admin','manager','supervisor')
def _forbidden(): return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền sử dụng Trung tâm ngoại lệ'),403
def _int(name): return int(request.args[name]) if request.args.get(name,'').strip() else None

# §3 of the 2026-08-28 Session Exception Resolution modal task: "Do NOT
# expose all Session fields blindly... derive authoritative rules from
# current MESFlow code. Do not invent edit capabilities." One entry per
# REAL detector in ExceptionRepository.detected_conditions() -- audited
# against that SQL directly, not guessed. Any exception_type not listed
# here (there are none today, but a future detector could land without
# this mapping being updated) gets an empty tuple -- no fields editable,
# fail closed rather than silently allow everything.
EDITABLE_FIELDS_BY_EXCEPTION_TYPE={
    # "Session mở quá lâu" -- the fix is closing it (or extending its
    # window via a real end time), never touching quantities.
    'LONG_OPEN_SESSION':('ended_at','status'),
    # "Operation đã hoàn tất nhưng Session còn mở" -- same fix shape.
    'OPERATION_COMPLETED_SESSION_OPEN':('ended_at','status'),
    # "Session quá giờ kết thúc ca" -- same fix shape.
    'SESSION_PAST_SHIFT_END':('ended_at','status'),
    # "Sản lượng bằng 0" on a long CLOSED session -- the real correction is
    # the quantities themselves, never start/end time or reassigning who/
    # what the session was.
    'ZERO_QUANTITY_LONG':('good_qty','defect_qty','rework_qty'),
    # "Thiếu thông tin trạm" -- exactly one field is wrong.
    'MISSING_STATION':('station_id',),
    # "Thời gian Session không hợp lệ" (ended_at < started_at) -- only the
    # timestamps themselves are the problem.
    'INVALID_DURATION':('started_at','ended_at'),
    # "Nhân viên có Session xung đột" -- fixed by adjusting one session's
    # window so the two no longer overlap (§3's "DUPLICATE_SESSION: provide
    # an explicit reconciliation action rather than arbitrary field
    # editing" -- adjusting the overlapping window IS that reconciliation
    # action for this detector's real shape; closing one session entirely
    # via `status` is the other common resolution).
    'EMPLOYEE_SESSION_CONFLICT':('started_at','ended_at','status'),
}

@bp.get('/exceptions')
@login_required
def list_exceptions():
    if not _allowed(): return _forbidden()
    try:
        ExceptionDetectionService().reconcile(getattr(g,'trace_id',''))
        view=str(request.args.get('view') or 'action').lower()
        statuses={'action':['OPEN','ACKNOWLEDGED'],'resolved':['RESOLVED'],'ignored':['AUTO_IGNORED','MANUAL_IGNORED']}.get(view)
        explicit=[x.strip().upper() for x in request.args.get('status','').split(',') if x.strip()]
        if explicit: statuses=explicit
        page=min(max(int(request.args.get('page',1)),1),100000);page_size=min(max(int(request.args.get('page_size',50)),1),200)
        result=ExceptionRepository().list(statuses=statuses,severity=request.args.get('severity','').upper(),exception_type=request.args.get('exception_type','').upper(),
          po_id=_int('po_id'),employee_id=_int('employee_id'),operation_id=_int('operation_id'),date_from=request.args.get('from',''),date_to=request.args.get('to',''),
          sort=request.args.get('sort','severity'),page=page,page_size=page_size)
        return jsonify(ok=True,view=view,**result)
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.get('/exceptions/<int:exception_id>')
@login_required
def exception_detail(exception_id):
    if not _allowed(): return _forbidden()
    try:return jsonify(ok=True,item=ExceptionRepository().get(exception_id))
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.get('/exceptions/<int:exception_id>/history')
@login_required
def exception_history(exception_id):
    if not _allowed(): return _forbidden()
    try:return jsonify(ok=True,items=ExceptionRepository().history(exception_id))
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

def _decision(exception_id,method):
    body=request.get_json(silent=True) or {}
    command=ExceptionDecisionCommand(exception_id,int(body.get('expected_version') or 0),session.get('user_id'),str(session.get('username') or ''),str(body.get('reason') or '').strip(),getattr(g,'trace_id',''))
    return jsonify(ok=True,item=getattr(ExceptionService(),method)(command))

@bp.post('/exceptions/<int:exception_id>/acknowledge')
@roles_required('admin','manager','supervisor')
def acknowledge(exception_id):
    try:return _decision(exception_id,'acknowledge')
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.post('/exceptions/<int:exception_id>/resolve')
@roles_required('admin','manager','supervisor')
def resolve(exception_id):
    try:return _decision(exception_id,'resolve')
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.post('/exceptions/<int:exception_id>/ignore')
@roles_required('admin','manager','supervisor')
def ignore(exception_id):
    try:return _decision(exception_id,'ignore')
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.get('/sessions/<int:session_id>/context')
@login_required
def session_context(session_id):
    if not _allowed(): return _forbidden()
    try:
        detail=ReportRepository().session_detail(session_id)
        detail['center_exceptions']=ExceptionRepository().for_session(session_id)
        return jsonify(ok=True,**detail)
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

# --- Inline Session Exception Resolution modal (2026-08-28) ---
# §1 of that task: replace "navigate to Session Management and scroll" with
# a first-class inline modal on the Exception Center page itself. These two
# endpoints are the only NEW API surface -- take/resolve/ignore already
# exist above (acknowledge/resolve/ignore) and are reused as-is, per §12's
# "reuse current APIs where practical."

@bp.get('/session-exceptions/<int:exception_id>/resolution-context')
@login_required
def resolution_context(exception_id):
    if not _allowed(): return _forbidden()
    try:
        item=ExceptionRepository().get(exception_id)
        history=ExceptionRepository().history(exception_id)
        session_row=None;activity=[]
        if item.get('session_id'):
            detail=ReportRepository().session_detail(item['session_id'])
            session_row=detail['session'];activity=detail['activity']
        # _json_safe(...), not a bare jsonify of the raw row: found live via
        # qa-center's session_exception_resolution_modal.py scenario --
        # Flask's default JSON provider serializes a bare datetime as RFC
        # 822 ("Thu, 27 Aug 2026 17:55:09 GMT"), while every OTHER place
        # this modal deals with updated_at (SessionChangedError's `current`,
        # edit_session()'s own comparison) uses _json_safe's ISO format. The
        # modal round-trips session.updated_at verbatim as expected_
        # updated_at on save -- with two different formats in play that
        # comparison would spuriously mismatch on every single save, not
        # just on a real concurrent edit.
        session_row=_json_safe(session_row) if session_row else session_row
        return jsonify(ok=True,exception=item,session=session_row,activity=activity,history=history,
            editable_fields=list(EDITABLE_FIELDS_BY_EXCEPTION_TYPE.get(item['exception_type'],())))
    except Exception as exc:return api_error_response(exc,logger_name=__name__)

@bp.post('/session-exceptions/<int:exception_id>/correct-session')
@roles_required('admin','manager','supervisor')
def correct_session(exception_id):
    try:
        item=ExceptionRepository().get(exception_id)
        session_id=item.get('session_id')
        if not session_id:
            raise ValueError('Ngoại lệ này không gắn với một Session cụ thể để sửa.')
        if item['status'] not in ('OPEN','ACKNOWLEDGED'):
            raise ConflictError('Ngoại lệ đã được xử lý, không thể sửa Session qua đây nữa.')
        allowed=EDITABLE_FIELDS_BY_EXCEPTION_TYPE.get(item['exception_type'],())
        body=request.get_json(silent=True) or {}
        # §3: only the fields this exception_type's own real detector cares
        # about are ever writable here -- anything else in the request body
        # (e.g. employee_id, operation_id for a type that never listed them)
        # is silently dropped, never passed through to edit_session().
        edit_data={k:body[k] for k in allowed if k in body}
        edit_data['reason']=str(body.get('reason') or '').strip()
        edit_data['request_id']=str(body.get('request_id') or '').strip()
        try:
            result=SupervisorRepository().edit_session(session_id,edit_data,session.get('user_id'),
                expected_updated_at=body.get('expected_updated_at'))
        except SessionChangedError as sc_exc:
            return jsonify(ok=False,error='SESSION_CHANGED',message=str(sc_exc),current=sc_exc.current),409
        AuditRepository().log(str(session.get('username') or ''),'SESSION_EXCEPTION_CORRECT_SESSION','exception',
            str(exception_id),{'session_id':session_id,'reason':edit_data['reason'],'fields':list(edit_data.keys()),
                               'old':result['old'],'new':result['item']})
        # §6/§9: re-run the SAME detector reconcile() every list load and
        # resolve() already use, so the modal can honestly tell the operator
        # whether the anomaly actually cleared -- never assumed just because
        # the edit itself succeeded.
        ExceptionDetectionService().reconcile(getattr(g,'trace_id',''))
        refreshed=ExceptionRepository().get(exception_id)
        cleared=refreshed['status'] not in ('OPEN','ACKNOWLEDGED') or not refreshed['condition_active']
        return jsonify(ok=True,old=result['old'],item=result['item'],exception=refreshed,cleared=cleared)
    except Exception as exc:return api_error_response(exc,logger_name=__name__)
