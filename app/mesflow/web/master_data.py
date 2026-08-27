from flask import Blueprint, jsonify, request, Response, session, g
import os
import re
from mesflow.web.auth import login_required,roles_required
from pathlib import Path
from uuid import uuid4
from mesflow.db.connection import transaction, fetch_all
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError
from mesflow.db.repositories.master_data import (
    EmployeeRepository,StationRepository,EquipmentRepository,SalesOrderRepository,
    ProductionOrderRepository,PartRepository,OperationRepository,TemplateRepository,TemplateTreeRepository,TemplateValidationError)
from mesflow.db.repositories.production_state import reconcile_production_order
from mesflow.db.repositories.analytics import AuditRepository
from mesflow.db.repositories.scheduling import RUNNABLE_STATUSES,RUNNABLE_PO_STATUSES
from mesflow.core.upload_policy import validate_drawing_upload
from mesflow.web.errors import api_error_response
from mesflow.domain.trace import record_event

bp=Blueprint('master_data',__name__,url_prefix='/api')
RESOURCES={
 'employees':EmployeeRepository(), 'stations':StationRepository(), 'equipment':EquipmentRepository(),
 'sales-orders':SalesOrderRepository(), 'production-orders':ProductionOrderRepository(),
 'parts':PartRepository(), 'operations':OperationRepository(), 'templates':TemplateRepository(),
}

def response_error(exc):
    constraint_name=getattr(getattr(exc,'diag',None),'constraint_name',None)
    if constraint_name == 'uq_parts_po_code':
        return jsonify(ok=False,error='DUPLICATE_PART_CODE',message='A part code is duplicated in the production order.'),409
    if isinstance(exc,TemplateValidationError):
        return jsonify(ok=False,error=exc.code,message=exc.message,details=exc.details),422
    return api_error_response(exc,logger_name=__name__)


UPLOAD_ROOT=Path('/data/uploads/template-parts')

DEMO_TEMPLATE_SOURCE='DEMO:E10GRE_ROUTER_V2_RELAXED'
DEMO_TEMPLATE_SOURCES=('DEMO:E10GRE_ROUTER_V1',DEMO_TEMPLATE_SOURCE)
DEMO_QUANTITY_LINKS={
    'DEMO-E10-CHI-TIET':{
        'THAN-THUNG-R-02':'THAN-THUNG-R-01',
        'AY-THUNG-RAC-03':'AY-THUNG-RAC-01',
        'QUAI-THUNG-R-04':'QUAI-THUNG-R-01',
    },
    'DEMO-E10-LAP-RAP':{
        'LAP-RAP-BAN--02':'LAP-RAP-BAN--01',
        'LAP-RAP-THAN-02':'LAP-RAP-THAN-01',
        'ONG-GOI-03':'ONG-GOI-01',
    },
    'DEMO-E10-FULL':{
        'THAN-THUNG-R-02':'THAN-THUNG-R-01',
        'AY-THUNG-RAC-03':'AY-THUNG-RAC-01',
        'LAP-RAP-BAN--02':'LAP-RAP-BAN--01',
        'LAP-RAP-THAN-02':'LAP-RAP-THAN-01',
        'ONG-GOI-03':'ONG-GOI-01',
    },
}
DEMO_TEMPLATES=[{'code': 'DEMO-E10-CHI-TIET',
  'name': 'E10GRE/SMR10GRE - Chi tiết',
  'product': 'Thùng rác E10GRE & SMR10GRE',
  'parts': [{'code': '10025-FB-201',
             'name': 'Thân thùng rác',
             'ops': [{'code': 'THAN-THUNG-R-01', 'name': 'CẮT PHÔI CHO THÂN THÙNG RÁC', 'seconds': 18},
                     {'code': 'THAN-THUNG-R-02', 'name': 'ĐỘT THÂN THÙNG RÁC', 'seconds': 30},
                     {'code': 'THAN-THUNG-R-03', 'name': 'CHẤN BƯỚC 1 ( Gấp Mí )', 'seconds': 20},
                     {'code': 'THAN-THUNG-R-04', 'name': 'CHẤN BƯỚC 2 ( Chấn Z )', 'seconds': 20},
                     {'code': 'THAN-THUNG-R-05', 'name': 'UỐN THÂN THÙNG RÁC', 'seconds': 30}]},
            {'code': '10025-FB-301',
             'name': 'Đáy thùng rác',
             'ops': [{'code': 'AY-THUNG-RAC-01', 'name': 'CẮT LASER ĐẾ THÙNG RÁC', 'seconds': 18},
                     {'code': 'AY-THUNG-RAC-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'AY-THUNG-RAC-03', 'name': 'DẬP ĐẾ THÙNG RÁC', 'seconds': 12}]},
            {'code': '10025-FB-306',
             'name': 'Nắp thùng rác',
             'ops': [{'code': 'NAP-THUNG-RA-01', 'name': 'CẮT LASER NẮP THÙNG RÁC', 'seconds': 18},
                     {'code': 'NAP-THUNG-RA-02', 'name': 'LÀM NGUỘI', 'seconds': 25}]},
            {'code': '10025-FB-302',
             'name': 'Quai thùng rác',
             'ops': [{'code': 'QUAI-THUNG-R-01', 'name': 'CẮT LASER CHO QUAI THÙNG RÁC', 'seconds': 18},
                     {'code': 'QUAI-THUNG-R-02', 'name': 'CẠO BAVIA', 'seconds': 25},
                     {'code': 'QUAI-THUNG-R-03', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'QUAI-THUNG-R-04', 'name': 'DẬP', 'seconds': 12},
                     {'code': 'QUAI-THUNG-R-05', 'name': 'UỐN', 'seconds': 30}]},
            {'code': '10025-FB-307',
             'name': 'Tay cầm',
             'ops': [{'code': 'TAY-CAM-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'TAY-CAM-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'TAY-CAM-03', 'name': 'CHẤN', 'seconds': 20}]},
            {'code': '10025-FB-303',
             'name': 'Bản lề A',
             'ops': [{'code': 'BAN-LE-A-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'BAN-LE-A-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'BAN-LE-A-03', 'name': 'DẬP', 'seconds': 12}]},
            {'code': '10025-FB-308',
             'name': 'Bản lề B',
             'ops': [{'code': 'BAN-LE-B-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'BAN-LE-B-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'BAN-LE-B-03', 'name': 'DẬP', 'seconds': 12},
                     {'code': 'BAN-LE-B-04', 'name': 'CHẤN', 'seconds': 20}]},
            {'code': '10025-FB-304',
             'name': 'Chốt Pin bản lề',
             'ops': [{'code': 'CHOT-PIN-BAN-01', 'name': 'DẬP CẮT', 'seconds': 18}]}]},
 {'code': 'DEMO-E10-LAP-RAP',
  'name': 'E10GRE/SMR10GRE - Lắp ráp',
  'product': 'Thùng rác E10GRE & SMR10GRE',
  'parts': [{'code': '10025-FB-309',
             'name': 'Lắp ráp bản lề',
             'ops': [{'code': 'LAP-RAP-BAN--01', 'name': 'LẮP RÁP BẢN LỀ', 'seconds': 45},
                     {'code': 'LAP-RAP-BAN--02', 'name': 'HÀN BẢN LỀ', 'seconds': 75}]},
            {'code': '10025-SA-305',
             'name': 'Hàn bản lề và tay cầm với nắp',
             'ops': [{'code': 'HAN-BAN-LE-V-01', 'name': 'HÀN BẢN LỀ VÀ TAY CẦM VỚI NẮP THÙNG RÁC', 'seconds': 75},
                     {'code': 'HAN-BAN-LE-V-02', 'name': 'VỆ SINH VÀ LÀM SẠCH SỈ HÀN', 'seconds': 75},
                     {'code': 'HAN-BAN-LE-V-03', 'name': 'SƠN TĨNH ĐIỆN', 'seconds': 30}]},
            {'code': '10025-SA-200',
             'name': 'Lắp ráp thân và đế thùng rác',
             'ops': [{'code': 'LAP-RAP-THAN-01', 'name': 'LẮP RÁP THÂN VÀ ĐẾ - RÚT RIVET', 'seconds': 45},
                     {'code': 'LAP-RAP-THAN-02', 'name': 'RÚT RIVET THÂN THÙNG RÁC', 'seconds': 45}]},
            {'code': '10025-SA-201',
             'name': 'HÀN THÂN VÀ ĐẾ SAU KHI LẮP RÁP',
             'ops': [{'code': 'HAN-THAN-VA--01', 'name': 'HÀN TIG TẠI VỊ TRÍ GHÉP MÍ', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--02', 'name': 'HÀN THÂN VÀ ĐẾ SAU KHI LẮP RÁP', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--03', 'name': 'VỆ SINH VÀ LÀ LÀM SẠCH SỈ HÀN', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--04', 'name': 'KHOAN LẠI LỖ LẮP QUAI THÙNG RÁC', 'seconds': 22},
                     {'code': 'HAN-THAN-VA--05', 'name': 'SƠN TĨNH ĐIỆN', 'seconds': 30}]},
            {'code': '10025-FB-310',
             'name': 'LẮP RÁP SAU KHI SƠN',
             'ops': [{'code': 'LAP-RAP-SAU--01', 'name': 'LẮP QUAI VỚI THÂN THÙNG RÁC', 'seconds': 30},
                     {'code': 'LAP-RAP-SAU--02', 'name': 'LẮP NẮP VỚI THÂN THÙNG RÁC', 'seconds': 30}]},
            {'code': 'ONG-GOI-PHU-KIEN',
             'name': 'Đóng gói phụ kiện',
             'ops': [{'code': 'ONG-GOI-PHU--01', 'name': 'ĐÓNG GÓI PHỤ KIỆN CHO THÙNG RÁC', 'seconds': 30}]},
            {'code': 'ONG-GOI',
             'name': 'ĐÓNG GÓI',
             'ops': [{'code': 'ONG-GOI-01', 'name': 'DÁN KEO CHO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-02', 'name': 'BẤM GHIM CHO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-03', 'name': 'VỆ SINH VÀ ĐÓNG GÓI', 'seconds': 25},
                     {'code': 'ONG-GOI-04', 'name': 'BỎ PHỤ KIỆN VÀ DÁN KEO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-05', 'name': 'ĐÁNH SỐ CHO THÙNG CARTON', 'seconds': 30},
                     {'code': 'ONG-GOI-06', 'name': 'XẾP PALLET', 'seconds': 30}]}]},
 {'code': 'DEMO-E10-FULL',
  'name': 'E10GRE/SMR10GRE - Toàn bộ quy trình',
  'product': 'Thùng rác E10GRE & SMR10GRE',
  'parts': [{'code': '10025-FB-201',
             'name': 'Thân thùng rác',
             'ops': [{'code': 'THAN-THUNG-R-01', 'name': 'CẮT PHÔI CHO THÂN THÙNG RÁC', 'seconds': 18},
                     {'code': 'THAN-THUNG-R-02', 'name': 'ĐỘT THÂN THÙNG RÁC', 'seconds': 30},
                     {'code': 'THAN-THUNG-R-03', 'name': 'CHẤN BƯỚC 1 ( Gấp Mí )', 'seconds': 20},
                     {'code': 'THAN-THUNG-R-04', 'name': 'CHẤN BƯỚC 2 ( Chấn Z )', 'seconds': 20},
                     {'code': 'THAN-THUNG-R-05', 'name': 'UỐN THÂN THÙNG RÁC', 'seconds': 30}]},
            {'code': '10025-FB-301',
             'name': 'Đáy thùng rác',
             'ops': [{'code': 'AY-THUNG-RAC-01', 'name': 'CẮT LASER ĐẾ THÙNG RÁC', 'seconds': 18},
                     {'code': 'AY-THUNG-RAC-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'AY-THUNG-RAC-03', 'name': 'DẬP ĐẾ THÙNG RÁC', 'seconds': 12}]},
            {'code': '10025-FB-306',
             'name': 'Nắp thùng rác',
             'ops': [{'code': 'NAP-THUNG-RA-01', 'name': 'CẮT LASER NẮP THÙNG RÁC', 'seconds': 18},
                     {'code': 'NAP-THUNG-RA-02', 'name': 'LÀM NGUỘI', 'seconds': 25}]},
            {'code': '10025-FB-302',
             'name': 'Quai thùng rác',
             'ops': [{'code': 'QUAI-THUNG-R-01', 'name': 'CẮT LASER CHO QUAI THÙNG RÁC', 'seconds': 18},
                     {'code': 'QUAI-THUNG-R-02', 'name': 'CẠO BAVIA', 'seconds': 25},
                     {'code': 'QUAI-THUNG-R-03', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'QUAI-THUNG-R-04', 'name': 'DẬP', 'seconds': 12},
                     {'code': 'QUAI-THUNG-R-05', 'name': 'UỐN', 'seconds': 30}]},
            {'code': '10025-FB-307',
             'name': 'Tay cầm',
             'ops': [{'code': 'TAY-CAM-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'TAY-CAM-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'TAY-CAM-03', 'name': 'CHẤN', 'seconds': 20}]},
            {'code': '10025-FB-303',
             'name': 'Bản lề A',
             'ops': [{'code': 'BAN-LE-A-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'BAN-LE-A-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'BAN-LE-A-03', 'name': 'DẬP', 'seconds': 12}]},
            {'code': '10025-FB-308',
             'name': 'Bản lề B',
             'ops': [{'code': 'BAN-LE-B-01', 'name': 'CẮT LASER', 'seconds': 18},
                     {'code': 'BAN-LE-B-02', 'name': 'LÀM NGUỘI', 'seconds': 25},
                     {'code': 'BAN-LE-B-03', 'name': 'DẬP', 'seconds': 12},
                     {'code': 'BAN-LE-B-04', 'name': 'CHẤN', 'seconds': 20}]},
            {'code': '10025-FB-304',
             'name': 'Chốt Pin bản lề',
             'ops': [{'code': 'CHOT-PIN-BAN-01', 'name': 'DẬP CẮT', 'seconds': 18}]},
            {'code': '10025-FB-309',
             'name': 'Lắp ráp bản lề',
             'ops': [{'code': 'LAP-RAP-BAN--01', 'name': 'LẮP RÁP BẢN LỀ', 'seconds': 45},
                     {'code': 'LAP-RAP-BAN--02', 'name': 'HÀN BẢN LỀ', 'seconds': 75}]},
            {'code': '10025-SA-305',
             'name': 'Hàn bản lề và tay cầm với nắp',
             'ops': [{'code': 'HAN-BAN-LE-V-01', 'name': 'HÀN BẢN LỀ VÀ TAY CẦM VỚI NẮP THÙNG RÁC', 'seconds': 75},
                     {'code': 'HAN-BAN-LE-V-02', 'name': 'VỆ SINH VÀ LÀM SẠCH SỈ HÀN', 'seconds': 75},
                     {'code': 'HAN-BAN-LE-V-03', 'name': 'SƠN TĨNH ĐIỆN', 'seconds': 30}]},
            {'code': '10025-SA-200',
             'name': 'Lắp ráp thân và đế thùng rác',
             'ops': [{'code': 'LAP-RAP-THAN-01', 'name': 'LẮP RÁP THÂN VÀ ĐẾ - RÚT RIVET', 'seconds': 45},
                     {'code': 'LAP-RAP-THAN-02', 'name': 'RÚT RIVET THÂN THÙNG RÁC', 'seconds': 45}]},
            {'code': '10025-SA-201',
             'name': 'HÀN THÂN VÀ ĐẾ SAU KHI LẮP RÁP',
             'ops': [{'code': 'HAN-THAN-VA--01', 'name': 'HÀN TIG TẠI VỊ TRÍ GHÉP MÍ', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--02', 'name': 'HÀN THÂN VÀ ĐẾ SAU KHI LẮP RÁP', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--03', 'name': 'VỆ SINH VÀ LÀ LÀM SẠCH SỈ HÀN', 'seconds': 75},
                     {'code': 'HAN-THAN-VA--04', 'name': 'KHOAN LẠI LỖ LẮP QUAI THÙNG RÁC', 'seconds': 22},
                     {'code': 'HAN-THAN-VA--05', 'name': 'SƠN TĨNH ĐIỆN', 'seconds': 30}]},
            {'code': '10025-FB-310',
             'name': 'LẮP RÁP SAU KHI SƠN',
             'ops': [{'code': 'LAP-RAP-SAU--01', 'name': 'LẮP QUAI VỚI THÂN THÙNG RÁC', 'seconds': 30},
                     {'code': 'LAP-RAP-SAU--02', 'name': 'LẮP NẮP VỚI THÂN THÙNG RÁC', 'seconds': 30}]},
            {'code': 'ONG-GOI-PHU-KIEN',
             'name': 'Đóng gói phụ kiện',
             'ops': [{'code': 'ONG-GOI-PHU--01', 'name': 'ĐÓNG GÓI PHỤ KIỆN CHO THÙNG RÁC', 'seconds': 30}]},
            {'code': 'ONG-GOI',
             'name': 'ĐÓNG GÓI',
             'ops': [{'code': 'ONG-GOI-01', 'name': 'DÁN KEO CHO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-02', 'name': 'BẤM GHIM CHO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-03', 'name': 'VỆ SINH VÀ ĐÓNG GÓI', 'seconds': 25},
                     {'code': 'ONG-GOI-04', 'name': 'BỎ PHỤ KIỆN VÀ DÁN KEO THÙNG CARTON', 'seconds': 35},
                     {'code': 'ONG-GOI-05', 'name': 'ĐÁNH SỐ CHO THÙNG CARTON', 'seconds': 30},
                     {'code': 'ONG-GOI-06', 'name': 'XẾP PALLET', 'seconds': 30}]}]}]

@bp.post('/template-parts/upload-drawing')
@roles_required('admin','manager')
def upload_template_part_drawing():
    file=request.files.get('file')
    if not file or not file.filename:
        return jsonify(ok=False,error='INVALID_REQUEST',message='No drawing file was selected.'),400
    try:
        validated=validate_drawing_upload(file)
        UPLOAD_ROOT.mkdir(parents=True,exist_ok=True)
        stored=f"{uuid4().hex}{validated.extension}"
        (UPLOAD_ROOT/stored).write_bytes(validated.data)
        return jsonify(ok=True,path=f'template-parts/{stored}',name=validated.original_name,url=f'/uploads/template-parts/{stored}'),201
    except Exception as exc:return response_error(exc)

@bp.get('/master/health')
def health():
    counts={name:len(repo.list(limit=1_000_000)) for name,repo in RESOURCES.items()}
    return jsonify(ok=True,backend='postgresql',phase='master-data',counts=counts)

@bp.get('/<resource>')
@login_required
def list_resource(resource):
    repo=RESOURCES.get(resource)
    if not repo: return jsonify(ok=False,error='UNKNOWN_RESOURCE'),404
    try:
        limit=min(int(request.args.get('limit',200)),1000); offset=max(int(request.args.get('offset',0)),0)
        items=repo.list_with_stats(limit=limit,offset=offset) if resource=='employees' else repo.list(limit=limit,offset=offset)
        return jsonify(ok=True,items=items)
    except Exception as exc: return response_error(exc)

@bp.post('/<resource>')
@roles_required('admin','manager')
def create_resource(resource):
    repo=RESOURCES.get(resource)
    if not repo: return jsonify(ok=False,error='UNKNOWN_RESOURCE'),404
    payload=request.get_json(silent=True) or {}
    try:
        if resource=='production-orders':
            template_id=int(payload.get('template_id') or payload.get('source_template_id') or 0)
            if template_id<=0:
                raise ValueError('Hãy chọn Template. Production Order không được tạo rỗng.')
            result=TemplateTreeRepository().instantiate(
                template_id,
                code=str(payload.get('code') or '').strip().upper(),
                planned_quantity=int(payload.get('planned_quantity') or 0),
                sales_order_id=payload.get('sales_order_id') or None,
                due_date=payload.get('due_date') or None,
                planned_start_at=payload.get('planned_start_at') or None,
                planned_end_at=payload.get('planned_end_at') or None,
                priority=str(payload.get('priority') or 'NORMAL').strip().upper(),
                notes=str(payload.get('notes') or '').strip(),
            )
            item=ProductionOrderRepository().get(result['production_order_id'])
            return jsonify(ok=True,id=result['production_order_id'],item=item,**result),201
        entity_id=repo.create(payload)
        return jsonify(ok=True,id=entity_id,item=repo.get(entity_id)),201
    except Exception as exc: return response_error(exc)

@bp.get('/templates/available-for-po')
@login_required
def available_templates_for_po():
    """Return active Templates with structure counts for every PO creation entry point."""
    try:
        with transaction() as conn:
            rows=conn.execute("""SELECT t.id,t.code,t.name,t.product,t.version,t.active,t.source_workbook,
                    COUNT(DISTINCT tp.id) AS part_count,COUNT(DISTINCT tpo.id) AS operation_count
                FROM templates t
                LEFT JOIN template_parts tp ON tp.template_id=t.id
                LEFT JOIN template_operations tpo ON tpo.template_id=t.id
                WHERE t.active=true
                GROUP BY t.id,t.code,t.name,t.product,t.version,t.active,t.source_workbook
                ORDER BY t.code,t.id""").fetchall()
        return jsonify(ok=True,items=[dict(row) for row in rows])
    except Exception as exc:
        return response_error(exc)


@bp.get('/operations/<int:operation_id>/material-flow')
@login_required
def operation_material_flow(operation_id):
    """Complete read-only Material Flow view for one Operation."""
    try:
        with transaction() as conn:
            op_row=conn.execute("""SELECT o.*,po.code po_code,po.planned_quantity,p.code part_code,p.name part_name,
                src.code input_source_code,src.name input_source_name,src.part_id input_source_part_id,
                src.done_qty input_source_done_qty,src.defect_qty input_source_defect_qty,src.rework_qty input_source_rework_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.target_operation_id=o.id),0) consumed_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id),0) allocated_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='GOOD'),0) good_allocated_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='REWORK'),0) rework_allocated_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.target_operation_id=o.id AND c.source_qty_kind='GOOD'),0) good_consumed_qty,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.target_operation_id=o.id AND c.source_qty_kind='REWORK'),0) rework_consumed_qty
                FROM operations o JOIN production_orders po ON po.id=o.production_order_id
                LEFT JOIN parts p ON p.id=o.part_id
                LEFT JOIN operations src ON src.id=o.input_source_operation_id
                WHERE o.id=%s""",(operation_id,)).fetchone()
            if not op_row:
                raise NotFoundError('Operation không tồn tại')

            items=conn.execute("""SELECT c.*,src.code source_code,src.name source_name,src.part_id source_part_id,
                tgt.code target_code,tgt.name target_name,tgt.part_id target_part_id,
                ws.status session_status,ws.started_at,ws.ended_at,e.employee_no,e.name employee_name
                FROM operation_input_consumptions c
                JOIN operations src ON src.id=c.source_operation_id
                JOIN operations tgt ON tgt.id=c.target_operation_id
                JOIN work_sessions ws ON ws.id=c.session_id
                LEFT JOIN employees e ON e.id=ws.employee_id
                WHERE c.source_operation_id=%s OR c.target_operation_id=%s
                ORDER BY c.updated_at DESC,c.id DESC""",(operation_id,operation_id)).fetchall()

            downstream=conn.execute("""SELECT o.id,o.code,o.name,o.part_id,p.code part_code,o.input_source_kind,
                COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed)
                          FROM operation_input_consumptions c
                          WHERE c.source_operation_id=%s AND c.target_operation_id=o.id),0) consumed_from_this_source
                FROM operations o LEFT JOIN parts p ON p.id=o.part_id
                WHERE o.input_flow_enabled=true AND o.input_source_operation_id=%s
                ORDER BY p.sort_order,o.sort_order,o.id""",(operation_id,operation_id)).fetchall()

            ledger_ids=[int(x['id']) for x in items]
            history=[]
            if ledger_ids:
                history=conn.execute("""SELECT h.* FROM operation_input_consumption_history h
                    WHERE h.ledger_id=ANY(%s) ORDER BY h.changed_at DESC,h.id DESC LIMIT 500""",(ledger_ids,)).fetchall()

            op=dict(op_row)
            produced=int(op.get('done_qty') or 0)
            rework=int(op.get('rework_qty') or 0)
            defect=int(op.get('defect_qty') or 0)
            allocated=int(op.get('allocated_qty') or 0)
            good_allocated=int(op.get('good_allocated_qty') or 0)
            rework_allocated=int(op.get('rework_allocated_qty') or 0)
            consumed=int(op.get('consumed_qty') or 0)
            source_kind=str(op.get('input_source_kind') or 'GOOD').upper()
            source_produced=int(op.get('input_source_rework_qty') or 0) if source_kind=='REWORK' else int(op.get('input_source_done_qty') or 0)
            source_allocated=0
            if op.get('input_source_operation_id'):
                source_allocated=int(conn.execute("""SELECT COALESCE(SUM(good_qty_consumed+defect_qty_consumed),0) qty
                    FROM operation_input_consumptions WHERE source_operation_id=%s AND source_qty_kind=%s""",
                    (op['input_source_operation_id'],source_kind)).fetchone()['qty'] or 0)

            relation={
                'enabled':bool(op.get('input_flow_enabled')),
                'source_operation_id':op.get('input_source_operation_id'),
                'source_code':op.get('input_source_code'),
                'source_name':op.get('input_source_name'),
                'source_kind':source_kind,
                'defects_consume_input':bool(op.get('defects_consume_input')),
                'source_pool_qty':source_produced,
                'source_pool_allocated_qty':source_allocated,
                'source_pool_available_qty':max(source_produced-source_allocated,0),
                'this_operation_consumed_qty':consumed,
            }
            return jsonify(ok=True,operation=op,relation=relation,summary={
                'produced_qty':produced,'rework_qty':rework,'scrap_qty':max(defect-rework,0),
                'allocated_qty':allocated,'available_qty':max(produced-good_allocated,0),
                'good_allocated_qty':good_allocated,'good_available_qty':max(produced-good_allocated,0),
                'rework_allocated_qty':rework_allocated,'rework_available_qty':max(rework-rework_allocated,0),
                'consumed_qty':consumed,
                'good_consumed_qty':int(op.get('good_consumed_qty') or 0),
                'rework_consumed_qty':int(op.get('rework_consumed_qty') or 0),
                'ledger_count':len(items),'history_count':len(history)},
                downstream=[dict(x) for x in downstream],
                items=[dict(x) for x in items],history=[dict(x) for x in history])
    except Exception as exc:
        return response_error(exc)

@bp.get('/<resource>/<entity_id>')
@login_required
def get_resource(resource,entity_id):
    repo=RESOURCES.get(resource)
    if not repo: return jsonify(ok=False,error='UNKNOWN_RESOURCE'),404
    try: return jsonify(ok=True,item=repo.get(entity_id))
    except Exception as exc: return response_error(exc)

@bp.patch('/<resource>/<entity_id>')
@roles_required('admin','manager')
def update_resource(resource,entity_id):
    repo=RESOURCES.get(resource)
    if not repo: return jsonify(ok=False,error='UNKNOWN_RESOURCE'),404
    try: return jsonify(ok=True,item=repo.update(entity_id,request.get_json(silent=True) or {}))
    except Exception as exc: return response_error(exc)

@bp.delete('/<resource>/<entity_id>')
@roles_required('admin','manager')
def delete_resource(resource,entity_id):
    repo=RESOURCES.get(resource)
    if not repo: return jsonify(ok=False,error='UNKNOWN_RESOURCE'),404
    try:
        repo.delete(entity_id)
        return jsonify(ok=True)
    except Exception as exc: return response_error(exc)


@bp.post('/production-orders/<int:po_id>/start')
@roles_required('admin','manager','supervisor')
def start_production_order(po_id):
    """Release a prepared PO to the shop floor and make its Operations available to kiosks."""
    try:
        with transaction() as conn:
            po=conn.execute('SELECT id,code,status FROM production_orders WHERE id=%s FOR UPDATE',(po_id,)).fetchone()
            if not po:
                raise NotFoundError('production order not found')
            current=str(po.get('status') or '').strip().upper()
            if current=='IN_PROGRESS':
                op_count=conn.execute('SELECT COUNT(*) AS n FROM operations WHERE production_order_id=%s',(po_id,)).fetchone()['n']
                return jsonify(ok=True,item=dict(po),operation_count=int(op_count or 0),already_started=True)
            if current in {'COMPLETED','CANCELLED'}:
                raise ConflictError('PO đã hoàn thành hoặc đã hủy nên không thể Start')
            op_count=int(conn.execute('SELECT COUNT(*) AS n FROM operations WHERE production_order_id=%s',(po_id,)).fetchone()['n'] or 0)
            if op_count<=0:
                raise ConflictError('PO chưa có Operation. Hãy thêm Operation trước khi Start.')
            started=conn.execute("""UPDATE production_orders
                SET status='IN_PROGRESS',updated_at=CURRENT_TIMESTAMP
                WHERE id=%s RETURNING *""",(po_id,)).fetchone()
            with conn.cursor() as cur:record_event(cur,event_type='PO_STARTED',category='PO',title='Production Order bắt đầu',po_id=po_id,
                actor_id=session.get('user_id'),actor_name=str(session.get('username') or ''),correlation_id=getattr(g,'trace_id',''),metadata={'previous_status':current,'status':'IN_PROGRESS'})
        return jsonify(ok=True,item=dict(started),operation_count=op_count,already_started=False)
    except Exception as exc:
        return response_error(exc)

@bp.post('/operations/<int:operation_id>/cancel')
@roles_required('admin','manager','supervisor')
def cancel_operation(operation_id):
    try:
        with transaction() as conn:
            operation=conn.execute('SELECT id,code,status,production_order_id FROM operations WHERE id=%s FOR UPDATE',(operation_id,)).fetchone()
            if not operation:raise NotFoundError('operation not found')
            if str(operation.get('status') or '').upper()=='COMPLETED':raise ConflictError('Operation đã COMPLETED, phải dùng workflow rework thay vì Cancel')
            opened=conn.execute("SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s AND status='OPEN'",(operation_id,)).fetchone()['n']
            if int(opened or 0):raise ConflictError('Operation còn Session OPEN; hãy đóng Session trước khi Cancel')
            conn.execute("UPDATE operations SET status='CANCELLED',updated_at=CURRENT_TIMESTAMP WHERE id=%s",(operation_id,))
            with conn.cursor() as cur:po=reconcile_production_order(cur,int(operation['production_order_id']))
        AuditRepository().log(str(session.get('username') or ''),'OPERATION_CANCEL','operation',str(operation_id),{'previous_status':operation['status']})
        return jsonify(ok=True,item=OperationRepository().get(operation_id),production_order=po)
    except Exception as exc:return response_error(exc)


@bp.delete('/production-orders/<int:po_id>/force')
@roles_required('admin')
def force_delete_production_order(po_id):
    """TEST ONLY: remove a PO and all execution data that blocks normal deletion."""
    if str(os.getenv('MESFLOW_ENABLE_FORCE_DELETE_PO','0')).strip().lower() not in {'1','true','yes','on'}:
        return jsonify(ok=False,error='FORCE_DELETE_DISABLED',message='Force Delete đã bị tắt trong cấu hình production'),403
    payload=request.get_json(silent=True) or {}
    try:
        with transaction() as conn:
            po=conn.execute('SELECT id,code,status,notes FROM production_orders WHERE id=%s FOR UPDATE',(po_id,)).fetchone()
            if not po:
                raise NotFoundError('production order not found')
            confirm_code=str(payload.get('confirm_code') or '').strip().upper()
            if confirm_code != str(po['code']).strip().upper():
                raise ValueError('Mã xác nhận không khớp. Hãy nhập đúng mã PO để Force Delete.')

            qa_run_id=str(payload.get('qa_run_id') or '').strip()
            qa_cleanup=bool(qa_run_id)
            if qa_cleanup:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{5,79}',qa_run_id):
                    raise ValueError('qa_run_id không hợp lệ')
                if str(po.get('notes') or '').strip() != f'QA_RUN_ID={qa_run_id}':
                    raise ConflictError('PO không thuộc QA run đã xác nhận; cleanup bị từ chối')

            history=conn.execute('''SELECT
                EXISTS(SELECT 1 FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id WHERE o.production_order_id=%s) has_sessions,
                EXISTS(SELECT 1 FROM operations o WHERE o.production_order_id=%s AND (COALESCE(o.done_qty,0)>0 OR COALESCE(o.defect_qty,0)>0 OR COALESCE(o.rework_qty,0)>0)) has_output,
                EXISTS(SELECT 1 FROM operation_input_consumptions c JOIN operations o ON o.id=c.source_operation_id OR o.id=c.target_operation_id WHERE o.production_order_id=%s) has_ledger,
                EXISTS(SELECT 1 FROM kiosk_events ke JOIN operations o ON o.id=ke.operation_id WHERE o.production_order_id=%s) has_events,
                EXISTS(SELECT 1 FROM operation_adjustments a JOIN operations o ON o.id=a.operation_id WHERE o.production_order_id=%s) has_adjustments,
                EXISTS(SELECT 1 FROM qc_inspections q JOIN operations o ON o.id=q.operation_id WHERE o.production_order_id=%s) has_qc,
                EXISTS(SELECT 1 FROM audit_logs a WHERE
                    (a.entity_type IN ('production_order','production_orders') AND a.entity_id=%s::text) OR
                    (a.entity_type IN ('operation','operations') AND a.entity_id IN (SELECT o.id::text FROM operations o WHERE o.production_order_id=%s))) has_audit''',
                (po_id,po_id,po_id,po_id,po_id,po_id,po_id,po_id)).fetchone() or {}
            labels={'has_sessions':'Session','has_output':'sản lượng','has_ledger':'ledger dòng vật tư',
                    'has_events':'event thực thi','has_adjustments':'lịch sử điều chỉnh','has_qc':'QC','has_audit':'audit'}
            found=[label for key,label in labels.items() if history.get(key)]
            if found and not qa_cleanup:
                raise ConflictError('Không thể Force Delete PO vì đã có production history: '+', '.join(found)+'. Dữ liệu thực thi phải được giữ để audit.')

            op_rows=conn.execute('SELECT id FROM operations WHERE production_order_id=%s',(po_id,)).fetchall()
            op_ids=[int(r['id']) for r in op_rows]
            part_rows=conn.execute('SELECT id FROM parts WHERE production_order_id=%s',(po_id,)).fetchall()
            part_ids=[int(r['id']) for r in part_rows]
            session_rows=[]
            if op_ids:
                session_rows=conn.execute('''SELECT id,start_request_id,finish_request_id
                    FROM work_sessions WHERE operation_id = ANY(%s)''',(op_ids,)).fetchall()
            session_ids=[int(r['id']) for r in session_rows]
            request_ids=[]
            for row in session_rows:
                if row.get('start_request_id'): request_ids.append(row['start_request_id'])
                if row.get('finish_request_id'): request_ids.append(row['finish_request_id'])

            counts={'operations':len(op_ids),'sessions':len(session_ids)}
            if qa_cleanup:
                counts['trace_events']=conn.execute('DELETE FROM production_trace_events WHERE production_order_id=%s OR operation_id = ANY(%s) OR session_id = ANY(%s)',(po_id,op_ids,session_ids)).rowcount
                counts['quantity_movements']=conn.execute('DELETE FROM quantity_movements WHERE production_order_id=%s OR operation_id = ANY(%s) OR session_id = ANY(%s)',(po_id,op_ids,session_ids)).rowcount
                counts['exceptions']=conn.execute('DELETE FROM exception_records WHERE production_order_id=%s OR operation_id = ANY(%s) OR session_id = ANY(%s)',(po_id,op_ids,session_ids)).rowcount
                counts['client_events']=conn.execute('DELETE FROM kiosk_client_events WHERE server_session_id = ANY(%s)',(session_ids,)).rowcount
                entity_ids=[str(po_id),*[str(x) for x in op_ids],*[str(x) for x in session_ids],*[str(x) for x in part_ids]]
                counts['audit_logs']=conn.execute("DELETE FROM audit_logs WHERE entity_id = ANY(%s) AND entity_type = ANY(%s)",(entity_ids,['production_order','production_orders','operation','operations','work_session','session','sessions','part','parts'])).rowcount
            if request_ids:
                result=conn.execute('DELETE FROM kiosk_idempotency WHERE request_id = ANY(%s)',(request_ids,))
                counts['idempotency']=result.rowcount
            else: counts['idempotency']=0
            if session_ids or op_ids:
                if session_ids and op_ids:
                    counts['kiosk_events']=conn.execute('DELETE FROM kiosk_events WHERE session_id = ANY(%s) OR operation_id = ANY(%s)',(session_ids,op_ids)).rowcount
                    counts['penalties']=conn.execute('DELETE FROM penalty_tickets WHERE session_id = ANY(%s) OR operation_id = ANY(%s)',(session_ids,op_ids)).rowcount
                    counts['adjustments']=conn.execute('DELETE FROM operation_adjustments WHERE session_id = ANY(%s) OR operation_id = ANY(%s)',(session_ids,op_ids)).rowcount
                    counts['qc']=conn.execute('DELETE FROM qc_inspections WHERE session_id = ANY(%s) OR operation_id = ANY(%s)',(session_ids,op_ids)).rowcount
                elif session_ids:
                    counts['kiosk_events']=conn.execute('DELETE FROM kiosk_events WHERE session_id = ANY(%s)',(session_ids,)).rowcount
                    counts['penalties']=conn.execute('DELETE FROM penalty_tickets WHERE session_id = ANY(%s)',(session_ids,)).rowcount
                    counts['adjustments']=conn.execute('DELETE FROM operation_adjustments WHERE session_id = ANY(%s)',(session_ids,)).rowcount
                    counts['qc']=conn.execute('DELETE FROM qc_inspections WHERE session_id = ANY(%s)',(session_ids,)).rowcount
                else:
                    counts['kiosk_events']=conn.execute('DELETE FROM kiosk_events WHERE operation_id = ANY(%s)',(op_ids,)).rowcount
                    counts['penalties']=conn.execute('DELETE FROM penalty_tickets WHERE operation_id = ANY(%s)',(op_ids,)).rowcount
                    counts['adjustments']=conn.execute('DELETE FROM operation_adjustments WHERE operation_id = ANY(%s)',(op_ids,)).rowcount
                    counts['qc']=conn.execute('DELETE FROM qc_inspections WHERE operation_id = ANY(%s)',(op_ids,)).rowcount
            if session_ids:
                counts['deleted_sessions']=conn.execute('DELETE FROM work_sessions WHERE id = ANY(%s)',(session_ids,)).rowcount
            else: counts['deleted_sessions']=0
            counts['parts']=conn.execute('SELECT COUNT(*) AS n FROM parts WHERE production_order_id=%s',(po_id,)).fetchone()['n']
            conn.execute('DELETE FROM production_orders WHERE id=%s',(po_id,))
        return jsonify(ok=True,qa_run_id=qa_run_id or None,deleted_po={'id':po_id,'code':po['code'],'status':po['status']},counts=counts)
    except Exception as exc:
        return response_error(exc)


@bp.post('/templates/demo/seed')
@roles_required('admin')
def seed_demo_templates():
    created=0
    updated=0
    skipped=0
    quantity_links=0
    try:
        with transaction() as conn:
            for template in DEMO_TEMPLATES:
                from mesflow.db.repositories.master_data import _validate_template_part_codes
                _validate_template_part_codes(template['parts'],template={'id':None,'code':template['code']})
                existing=conn.execute('SELECT id,source_workbook FROM templates WHERE code=%s',(template['code'],)).fetchone()
                if existing and str(existing.get('source_workbook') or '') not in DEMO_TEMPLATE_SOURCES:
                    skipped+=1
                    continue
                if existing:
                    tpl={'id':existing['id']}
                    conn.execute("""UPDATE templates SET name=%s,product=%s,version='DEMO-2.0',active=true,
                        source_workbook=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                        (template['name'],template['product'],DEMO_TEMPLATE_SOURCE,tpl['id']))
                    conn.execute('DELETE FROM template_operations WHERE template_id=%s',(tpl['id'],))
                    conn.execute('DELETE FROM template_equipment WHERE template_id=%s',(tpl['id'],))
                    conn.execute('DELETE FROM template_parts WHERE template_id=%s',(tpl['id'],))
                    updated+=1
                else:
                    tpl=conn.execute("""INSERT INTO templates(code,name,product,version,active,source_workbook)
                        VALUES(%s,%s,%s,'DEMO-2.0',true,%s) RETURNING id""",
                        (template['code'],template['name'],template['product'],DEMO_TEMPLATE_SOURCE)).fetchone()
                    created+=1
                links=DEMO_QUANTITY_LINKS.get(template['code'],{})
                for p_index,part in enumerate(template['parts']):
                    part_row=conn.execute("""INSERT INTO template_parts(template_id,code,name,drawing_path,sort_order)
                        VALUES(%s,%s,%s,'',%s) RETURNING id""",
                        (tpl['id'],str(part['code'])[:80],part['name'],p_index)).fetchone()
                    for o_index,op in enumerate(part['ops']):
                        op_code=str(op['code'])[:80]
                        source_code=links.get(op_code)
                        conn.execute("""INSERT INTO template_operations(
                            template_id,part_id,code,name,sort_order,equipment_code,
                            standard_seconds_per_unit,input_flow_enabled,input_source_code,defects_consume_input)
                            VALUES(%s,%s,%s,%s,%s,'',%s,%s,%s,true)""",
                            (tpl['id'],part_row['id'],op_code,op['name'],o_index,float(op['seconds']),
                             bool(source_code),source_code))
                        if source_code:
                            quantity_links+=1
        return jsonify(ok=True,created=created,updated=updated,skipped=skipped,total=len(DEMO_TEMPLATES),quantity_links=quantity_links,version='DEMO-2.0')
    except Exception as exc:
        return response_error(exc)

@bp.delete('/templates/demo')
@roles_required('admin')
def delete_demo_templates():
    try:
        with transaction() as conn:
            rows=conn.execute('SELECT id FROM templates WHERE source_workbook = ANY(%s)',(list(DEMO_TEMPLATE_SOURCES),)).fetchall()
            ids=[row['id'] for row in rows]
            if ids:
                conn.execute('DELETE FROM templates WHERE source_workbook = ANY(%s)',(list(DEMO_TEMPLATE_SOURCES),))
        return jsonify(ok=True,deleted=len(ids))
    except Exception as exc:
        return response_error(exc)

@bp.get('/templates/<int:template_id>/tree')
@login_required
def template_tree(template_id):
    try: return jsonify(ok=True,**TemplateTreeRepository().get(template_id))
    except Exception as exc: return response_error(exc)

@bp.put('/templates/<int:template_id>/tree')
@roles_required('admin','manager')
def replace_template_tree(template_id):
    try: return jsonify(ok=True,**TemplateTreeRepository().replace_tree(template_id,request.get_json(silent=True) or {}))
    except Exception as exc: return response_error(exc)



@bp.get('/templates/<int:template_id>/validate')
@login_required
def validate_template(template_id):
    try:
        result=TemplateTreeRepository().validate(template_id)
        return jsonify(ok=True,**result)
    except Exception as exc:
        return response_error(exc)

@bp.post('/templates/<int:template_id>/instantiate')
@roles_required('admin','manager')
def instantiate_template(template_id):
    payload=request.get_json(silent=True) or {}
    try:
        result=TemplateTreeRepository().instantiate(
            template_id,
            code=str(payload.get('code') or '').strip().upper(),
            planned_quantity=int(payload.get('planned_quantity') or 0),
            sales_order_id=payload.get('sales_order_id') or None,
            due_date=payload.get('due_date') or None,
            planned_start_at=payload.get('planned_start_at') or None,
            planned_end_at=payload.get('planned_end_at') or None,
            priority=str(payload.get('priority') or 'NORMAL').strip().upper(),
            notes=str(payload.get('notes') or '').strip(),
        )
        return jsonify(ok=True,**result),201
    except Exception as exc:
        return response_error(exc)


@bp.get('/qr-labels')
@login_required
def qr_labels():
    """Unified printable QR catalogue for employees and shop-floor entities."""
    try:
        kind=str(request.args.get('type') or 'EMPLOYEE').strip().upper()
        q=str(request.args.get('q') or '').strip()
        po_id=request.args.get('production_order_id')
        active_only=str(request.args.get('active_only') or '1').lower() not in ('0','false','no')
        limit=max(1,min(int(request.args.get('limit') or 2000),5000))
        like=f'%{q}%'
        params=[]
        if kind=='EMPLOYEE':
            # Keep the QR catalogue compatible with databases created by older
            # MESFlow releases. Only core employee columns are required here;
            # optional profile fields must never make the whole QR screen fail.
            sql="""SELECT e.id,'EMPLOYEE' AS qr_type,e.employee_no AS code,e.name,
                CASE WHEN COALESCE(e.qr,'')='' THEN 'WF|EMP|'||e.employee_no ELSE e.qr END AS qr_payload,
                ''::text AS group_name,''::text AS detail,
                COALESCE(e.active,true) AS active,NULL::bigint AS production_order_id,NULL::text AS po_code
                FROM employees e
                WHERE (%s='' OR e.employee_no ILIKE %s OR e.name ILIKE %s)"""
            params=[q,like,like]
            if active_only: sql+=' AND COALESCE(e.active,true)=true'
            sql+=' ORDER BY e.employee_no LIMIT %s'; params.append(limit)
        elif kind=='OPERATION':
            # An operation is only actually scannable/startable at the kiosk
            # when BOTH its own status and its parent PO's status are in the
            # "runnable" sets kiosk_v2.py/execution.py enforce at scan time
            # (see scheduling.py's operation_wip()/dispatch_state_from_db()
            # -- the single source of truth reused here, not duplicated, so
            # this list can never silently drift out of sync with what the
            # kiosk actually accepts). Real bug reported live: a COMPLETED/
            # CANCELLED operation, or one whose PO hasn't been Started yet,
            # still had a printed/printable QR code here -- scanning it at
            # the kiosk then failed with OPERATION_NOT_WORKABLE, an error
            # that was entirely avoidable by just not listing it in the
            # first place. Gated behind active_only (default true, same
            # flag EMPLOYEE/PART already use) so the full, unfiltered
            # catalogue is still available on request (e.g. for auditing
            # already-printed labels), not permanently hidden.
            runnable_status_ph=','.join(['%s']*len(RUNNABLE_STATUSES))
            runnable_po_ph=','.join(['%s']*len(RUNNABLE_PO_STATUSES))
            sql=f"""SELECT o.id,'OPERATION' AS qr_type,o.code,o.name,
                COALESCE(NULLIF(o.qr,''),'WF|OP|'||o.code) AS qr_payload,
                po.code AS group_name,p.code||' · '||COALESCE(p.name,'') AS detail,
                (o.status IN ({runnable_status_ph}) AND po.status IN ({runnable_po_ph})) AS active,
                po.id AS production_order_id,po.code AS po_code
                FROM operations o JOIN production_orders po ON po.id=o.production_order_id
                JOIN parts p ON p.id=o.part_id
                WHERE (%s='' OR o.code ILIKE %s OR o.name ILIKE %s OR po.code ILIKE %s OR p.code ILIKE %s)"""
            params=list(RUNNABLE_STATUSES)+list(RUNNABLE_PO_STATUSES)+[q,like,like,like,like]
            if active_only:
                sql+=f' AND o.status IN ({runnable_status_ph}) AND po.status IN ({runnable_po_ph})'
                params+=list(RUNNABLE_STATUSES)+list(RUNNABLE_PO_STATUSES)
            if po_id: sql+=' AND po.id=%s'; params.append(int(po_id))
            sql+=' ORDER BY po.code,p.sort_order,o.sort_order,o.id LIMIT %s'; params.append(limit)
        elif kind=='PART':
            sql="""SELECT p.id,'PART' AS qr_type,p.code,p.name,
                'WF|PART|'||p.code AS qr_payload,po.code AS group_name,
                COALESCE(p.name,'') AS detail,p.active,po.id AS production_order_id,po.code AS po_code
                FROM parts p JOIN production_orders po ON po.id=p.production_order_id
                WHERE (%s='' OR p.code ILIKE %s OR p.name ILIKE %s OR po.code ILIKE %s)"""
            params=[q,like,like,like]
            if active_only: sql+=' AND p.active=true'
            if po_id: sql+=' AND po.id=%s'; params.append(int(po_id))
            sql+=' ORDER BY po.code,p.sort_order,p.id LIMIT %s'; params.append(limit)
        elif kind=='PRODUCTION_ORDER':
            sql="""SELECT po.id,'PRODUCTION_ORDER' AS qr_type,po.code,po.product AS name,
                'WF|PO|'||po.code AS qr_payload,po.status AS group_name,
                'Kế hoạch: '||po.planned_quantity::text AS detail,true AS active,
                po.id AS production_order_id,po.code AS po_code
                FROM production_orders po
                WHERE (%s='' OR po.code ILIKE %s OR po.product ILIKE %s)
                ORDER BY po.id DESC LIMIT %s"""
            params=[q,like,like,limit]
        else:
            return jsonify(ok=False,error='INVALID_QR_TYPE',message='Loại QR không hợp lệ.'),400
        return jsonify(ok=True,items=fetch_all(sql,tuple(params)),type=kind)
    except Exception as exc:
        return response_error(exc)

@bp.get('/qr-image')
@login_required
def qr_image():
    try:
        payload=str(request.args.get('data') or '')
        if not payload or len(payload)>512:
            return jsonify(ok=False,error='INVALID_QR_DATA',message='Nội dung QR không hợp lệ.'),400
        import qrcode
        import qrcode.image.svg
        factory=qrcode.image.svg.SvgPathImage
        img=qrcode.make(payload,image_factory=factory,box_size=8,border=2,error_correction=qrcode.constants.ERROR_CORRECT_M)
        from io import BytesIO
        out=BytesIO(); img.save(out)
        return Response(out.getvalue(),mimetype='image/svg+xml',headers={'Cache-Control':'private, max-age=3600'})
    except Exception as exc:
        return response_error(exc)
