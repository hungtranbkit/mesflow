from flask import Blueprint,jsonify,request,session
from mesflow.services.production_trace_service import ProductionTraceService
from mesflow.web.auth import login_required
from mesflow.web.errors import api_error_response
bp=Blueprint('production_trace',__name__,url_prefix='/api')
def allowed():return str(session.get('role') or '').lower() in ('admin','manager','supervisor')
def get_trace(kind,id):
    if not allowed():return jsonify(ok=False,error='FORBIDDEN',message='Không có quyền xem Production Trace'),403
    try:
        cats=[x for x in request.args.get('category','').upper().split(',') if x]
        data=ProductionTraceService().trace(kind,id,limit=min(max(int(request.args.get('limit',100)),1),200),before=request.args.get('before') or None,categories=cats or None,operation_id=request.args.get('operation_id') or None,employee_id=request.args.get('employee_id') or None,include_audit=str(session.get('role')).lower()=='admin')
        return jsonify(ok=True,**data)
    except Exception as exc:return api_error_response(exc,logger_name=__name__)
@bp.get('/production-orders/<int:id>/trace')
@login_required
def po(id):return get_trace('po',id)
@bp.get('/operations/<int:id>/trace')
@login_required
def operation(id):return get_trace('operation',id)
@bp.get('/sessions/<int:id>/trace')
@login_required
def work_session(id):return get_trace('session',id)
@bp.get('/<kind>/<int:id>/quantity-history')
@login_required
def quantities(kind,id):
    if not allowed():return jsonify(ok=False,error='FORBIDDEN'),403
    mapped={'production-orders':'po','operations':'operation','sessions':'session'}.get(kind)
    if not mapped:return jsonify(ok=False,error='NOT_FOUND'),404
    try:return jsonify(ok=True,**ProductionTraceService().quantity_history(mapped,id,int(request.args.get('limit',200))))
    except Exception as exc:return api_error_response(exc,logger_name=__name__)
