"""V67 Exception Center HTTP adapter; business transitions stay in services."""
from flask import Blueprint,g,jsonify,request,session
from mesflow.db.repositories.analytics import ReportRepository
from mesflow.db.repositories.exceptions import ExceptionRepository
from mesflow.services.exception_service import ExceptionDecisionCommand,ExceptionDetectionService,ExceptionService
from mesflow.web.auth import login_required,roles_required
from mesflow.web.errors import api_error_response

bp=Blueprint('exceptions',__name__,url_prefix='/api')

def _allowed(): return str(session.get('role') or '').lower() in ('admin','manager','supervisor')
def _forbidden(): return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền sử dụng Trung tâm ngoại lệ'),403
def _int(name): return int(request.args[name]) if request.args.get(name,'').strip() else None

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
