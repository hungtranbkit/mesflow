from __future__ import annotations

import uuid
from flask import Blueprint, jsonify, request, render_template

from mesflow import __version__
from mesflow.db.connection import fetch_one, fetch_all
from mesflow.db.repositories.execution import KioskRepository, WorkSessionRepository
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError

bp = Blueprint('web_kiosk', __name__)


def _error(exc):
    message = str(exc) or 'Không thể xử lý yêu cầu'
    lowered = message.lower()
    if isinstance(exc, NotFoundError):
        return jsonify(ok=False, error='NOT_FOUND', error_code='DAT-404', message=message,
                       action='Kiểm tra mã QR hoặc dữ liệu đã được khai báo trên MESFlow.'), 404
    if isinstance(exc, ConflictError):
        code = 'SES-409'
        action = 'Quét lại thẻ nhân viên. Nếu vẫn lỗi, báo quản đốc kiểm tra phiên đang mở.'
        if 'chưa bắt đầu session' in lowered or 'start session op nguồn' in lowered:
            code, action = 'DEP-409', 'Start session của OP nguồn trước, sau đó quét lại OP hiện tại.'
        elif 'input' in lowered or 'available' in lowered or 'sản lượng' in lowered or 'đầu vào' in lowered:
            code, action = 'QTY-409', 'Kết thúc session OP nguồn và nhập đủ sản lượng, hoặc giảm số lượng OP hiện tại.'
        return jsonify(ok=False, error='CONFLICT', error_code=code, message=message, action=action), 409
    if isinstance(exc, (ValueError, RepositoryError, KeyError, TypeError)):
        return jsonify(ok=False, error='INVALID_REQUEST', error_code='REQ-400', message=message,
                       action='Quét lại đúng thứ tự hoặc nhập lại dữ liệu.'), 400
    return jsonify(ok=False, error='INTERNAL_ERROR', error_code='SYS-500',
                   message='Máy chủ không xử lý được yêu cầu.',
                   action='Ghi lại mã SYS-500 và báo người quản trị.', detail=f'{type(exc).__name__}: {exc}'), 500


def _normalize_qr(value: object) -> str:
    return str(value or '').strip()


@bp.get('/kiosk')
def kiosk_page():
    return render_template('kiosk.html', version=__version__)


@bp.get('/api/kiosk-web/health')
def kiosk_health():
    return jsonify(ok=True, version=__version__, module='web-kiosk')


@bp.post('/api/kiosk-web/heartbeat')
def kiosk_web_heartbeat():
    body = request.get_json(silent=True) or {}
    try:
        device_uuid = str(body.get('device_uuid') or '').strip()
        if not device_uuid:
            raise ValueError('device_uuid required')
        status = KioskRepository().heartbeat_web_demo(device_uuid, body)
        return jsonify(ok=True, status=dict(status))
    except Exception as exc:
        return _error(exc)


@bp.get('/api/kiosk-web/demo-data')
def kiosk_demo_data():
    """Danh sách QR để mô phỏng máy quét trên màn hình kiosk."""
    try:
        employees = fetch_all(
            """SELECT id, employee_no, name, department, position, qr
               FROM employees
               WHERE active=TRUE
               ORDER BY employee_no, name
               LIMIT 300"""
        )
        operations = fetch_all(
            """SELECT o.id,o.code,o.name,o.qr,o.status,COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
                      p.code part_code,p.name part_name,po.code po_code,po.product
               FROM operations o
               LEFT JOIN parts p ON p.id=o.part_id
               LEFT JOIN production_orders po ON po.id=o.production_order_id
               WHERE UPPER(TRIM(COALESCE(po.status,'')))='IN_PROGRESS'
                 AND UPPER(TRIM(COALESCE(o.status,''))) NOT IN ('COMPLETED','CANCELLED')
               ORDER BY po.code NULLS LAST,p.sort_order NULLS LAST,p.id,o.sort_order NULLS LAST,o.id
               LIMIT 500"""
        )
        return jsonify(
            ok=True,
            employees=[dict(row) for row in employees],
            operations=[dict(row) for row in operations],
        )
    except Exception as exc:
        return _error(exc)


@bp.post('/api/kiosk-web/scan')
def kiosk_scan():
    body = request.get_json(silent=True) or {}
    qr = _normalize_qr(body.get('qr'))
    if not qr:
        return jsonify(ok=False, error='QR_REQUIRED', error_code='SCN-001', message='Chưa nhận được mã quét', action='Kiểm tra nguồn và dây máy quét, rồi quét lại.'), 400

    if qr.upper().startswith('WF|EMP|'):
        employee = fetch_one(
            """SELECT id,employee_no,name,department,position,active,employment_status,qr
               FROM employees
               WHERE upper(qr)=upper(%s) OR upper(employee_no)=upper(%s)
               LIMIT 1""",
            (qr, qr.split('|')[-1]),
        )
        if not employee or not employee['active']:
            return jsonify(ok=False, error='EMPLOYEE_NOT_FOUND', error_code='EMP-001', message='Không tìm thấy nhân viên đang hoạt động', action='Quét đúng thẻ nhân viên hoặc nhờ quản đốc kiểm tra trạng thái nhân viên.'), 404
        opened = fetch_one(
            """SELECT s.id,s.employee_id,s.operation_id,s.started_at,s.station_id,
                      o.code operation_code,o.name operation_name,COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
                      p.code part_code,p.name part_name,po.code po_code,po.product
               FROM work_sessions s
               JOIN operations o ON o.id=s.operation_id
               LEFT JOIN parts p ON p.id=o.part_id
               LEFT JOIN production_orders po ON po.id=o.production_order_id
               WHERE s.employee_id=%s AND s.status='OPEN'
               ORDER BY s.id DESC LIMIT 1""",
            (employee['id'],),
        )
        return jsonify(ok=True, type='employee', employee=dict(employee), open_session=dict(opened) if opened else None)

    if qr.upper().startswith('WF|OP|'):
        operation = fetch_one(
            """SELECT o.id,o.code,o.name,o.qr,o.status,COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
                      o.part_id,o.production_order_id,p.code part_code,p.name part_name,
                      po.code po_code,po.product,po.status po_status
               FROM operations o
               LEFT JOIN parts p ON p.id=o.part_id
               LEFT JOIN production_orders po ON po.id=o.production_order_id
               WHERE upper(o.qr)=upper(%s) OR upper(o.code)=upper(%s)
               LIMIT 1""",
            (qr, qr.split('|')[-1]),
        )
        if not operation:
            return jsonify(ok=False, error='OPERATION_NOT_FOUND', error_code='OP-001', message='Không tìm thấy Operation', action='Kiểm tra QR Operation hoặc tạo lại QR từ PO.'), 404
        if str(operation.get('po_status') or '').upper() != 'IN_PROGRESS':
            return jsonify(ok=False, error='PO_NOT_STARTED', error_code='PO-001', message=f"PO {operation.get('po_code') or ''} chưa Start hoặc đang tạm dừng", action='Nhờ quản đốc bấm Start/Tiếp tục PO trên màn hình quản lý.'), 409
        return jsonify(ok=True, type='operation', operation=dict(operation))

    return jsonify(ok=False, error='UNSUPPORTED_QR', error_code='SCN-002', message='Sai định dạng QR', action='QR hợp lệ phải bắt đầu bằng WF|EMP| hoặc WF|OP|.'), 400


@bp.post('/api/kiosk-web/start')
def kiosk_start():
    body = request.get_json(silent=True) or {}
    try:
        payload = {
            'request_id': str(body.get('request_id') or f'WEB-START-{uuid.uuid4()}'),
            'employee_id': int(body['employee_id']),
            'operation_id': int(body['operation_id']),
            'station_id': int(body['station_id']) if body.get('station_id') else None,
            'device_uuid': str(body.get('device_uuid') or 'WEB-KIOSK'),
        }
        return jsonify(WorkSessionRepository().start(payload)), 201
    except Exception as exc:
        return _error(exc)


@bp.post('/api/kiosk-web/finish/<int:session_id>')
def kiosk_finish(session_id: int):
    body = request.get_json(silent=True) or {}
    try:
        payload = {
            'request_id': str(body.get('request_id') or f'WEB-FINISH-{uuid.uuid4()}'),
            'good_qty': max(int(body.get('good_qty') or 0), 0),
            'defect_qty': max(int(body.get('defect_qty') or 0), 0),
            'rework_qty': max(int(body.get('rework_qty') or 0), 0),
            'note': str(body.get('note') or '').strip(),
        }
        return jsonify(WorkSessionRepository().finish(session_id, payload))
    except Exception as exc:
        return _error(exc)
