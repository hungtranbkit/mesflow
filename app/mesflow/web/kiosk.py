from __future__ import annotations

import uuid
from flask import Blueprint, jsonify, request, render_template

from mesflow import __version__
from mesflow.web.auth import login_required, production_client_required
from mesflow.db.connection import fetch_one, fetch_all
from mesflow.db.repositories.execution import KioskRepository, WorkSessionRepository
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError
from mesflow.domain.errors import PermissionDeniedError

bp = Blueprint('web_kiosk', __name__)


def _error(exc):
    message = str(exc) or 'Không thể xử lý yêu cầu'
    lowered = message.lower()
    if isinstance(exc, NotFoundError):
        return jsonify(ok=False, error='NOT_FOUND', error_code='DAT-404', message=message,
                       action='Kiểm tra mã QR hoặc dữ liệu đã được khai báo trên KIMEX.'), 404
    if isinstance(exc, ConflictError):
        code = 'SES-409'
        action = 'Quét lại thẻ nhân viên. Nếu vẫn lỗi, báo quản đốc kiểm tra phiên đang mở.'
        if 'chưa bắt đầu session' in lowered or 'start session op nguồn' in lowered:
            code, action = 'DEP-409', 'Start session của OP nguồn trước, sau đó quét lại OP hiện tại.'
        elif 'input' in lowered or 'available' in lowered or 'sản lượng' in lowered or 'đầu vào' in lowered:
            code, action = 'QTY-409', 'Kết thúc session OP nguồn và nhập đủ sản lượng, hoặc giảm số lượng OP hiện tại.'
        return jsonify(ok=False, error='CONFLICT', error_code=code, message=message, action=action), 409
    if isinstance(exc, PermissionDeniedError):
        return jsonify(ok=False, error='FORBIDDEN', error_code='AUTH-403', message=message,
                       action='Liên hệ quản trị viên để kiểm tra trạng thái kiosk.'), 403
    if isinstance(exc, (ValueError, RepositoryError, KeyError, TypeError)):
        return jsonify(ok=False, error='INVALID_REQUEST', error_code='REQ-400', message=message,
                       action='Quét lại đúng thứ tự hoặc nhập lại dữ liệu.'), 400
    return jsonify(ok=False, error='INTERNAL_ERROR', error_code='SYS-500',
                   message='Máy chủ không xử lý được yêu cầu.',
                   action='Ghi lại mã SYS-500 và báo người quản trị.'), 500


def _normalize_qr(value: object) -> str:
    return str(value or '').strip()


@bp.get('/kiosk')
def kiosk_page():
    return render_template('kiosk.html', version=__version__)


# P1 fix (2026-08-28 business-logic audit): this route never existed --
# templates/wallboard_employee_productivity.html + static/wallboard-
# employee-productivity.js + static/wallboard.css were all fully built
# (the template's own comment already documents it as reading exactly
# /api/wallboard/employee-productivity, which itself was ALSO missing
# until this same audit pass -- see app/mesflow/web/analytics.py), but
# nothing ever served the page itself at the URL the JS/tests expect. The
# public employee-productivity wallboard was 100% unreachable in
# production, not merely broken. PUBLIC (no login) -- same posture as
# /kiosk above: the TV/kiosk display has no one signed in.
@bp.get('/kiosk/employee-productivity')
def employee_productivity_wallboard_page():
    return render_template('wallboard_employee_productivity.html', version=__version__)


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
        # Lets an already-open kiosk tab notice a new deploy on its own --
        # kiosk.js compares this to the version it loaded with and reloads
        # itself when idle. Without this, a kiosk machine an operator can't
        # reach (locked keyboard, no remote access) keeps running whatever
        # JS/CSS was in the browser at last page load forever, regardless
        # of how many times the server gets redeployed.
        return jsonify(ok=True, status=dict(status), version=__version__)
    except Exception as exc:
        return _error(exc)


@bp.get('/api/kiosk-web/demo-data')
@login_required
def kiosk_demo_data():
    """Danh sách QR để mô phỏng máy quét trên màn hình kiosk.

    Signed-in only. This returns the full employee roster including every
    badge QR value, which is a credential: anyone holding it can identify as
    that worker at any terminal. It exists purely so an admin can demo a scan
    without a physical scanner -- a real terminal never calls it, because a
    real scanner types into the input field. It was reachable unauthenticated
    from the public internet until 2026-09-09.
    """
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
@production_client_required
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
                      o.code operation_code,o.name operation_name,o.operation_type,
                      CASE WHEN strpos(upper(o.code),upper(p.code))>0 THEN o.code
                           ELSE p.code||'-'||o.code END operation_display_key,
                      COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
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

    # Two payload shapes, one code path. `WF|OP|<code>` is what the labels
    # already printed in the workshop carry; `WF|OPID|<id>` is what new labels
    # (every SETUP label included) carry, because an Operation code is only
    # unique within its Part and so cannot be a durable identifier.
    upper = qr.upper()
    if upper.startswith('WF|OP|') or upper.startswith('WF|OPID|'):
        key = qr.split('|')[-1]
        by_id = upper.startswith('WF|OPID|') and key.isdigit()
        operation = fetch_one(
            """SELECT o.id,o.code,o.name,o.qr,o.status,COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
                      o.operation_type,o.requires_setup,o.setup_completed_at,o.parent_operation_id,
                      o.part_id,o.production_order_id,p.code part_code,p.name part_name,
                      CASE WHEN strpos(upper(o.code),upper(p.code))>0 THEN o.code
                           ELSE p.code||'-'||o.code END display_key,
                      po.code po_code,po.product,po.status po_status
               FROM operations o
               LEFT JOIN parts p ON p.id=o.part_id
               LEFT JOIN production_orders po ON po.id=o.production_order_id
               WHERE """ + ('o.id=%s' if by_id else 'upper(o.qr)=upper(%s) OR upper(o.code)=upper(%s)') + """
               LIMIT 1""",
            (int(key),) if by_id else (qr, key),
        )
        if not operation:
            return jsonify(ok=False, error='OPERATION_NOT_FOUND', error_code='OP-001', message='Không tìm thấy Operation', action='Kiểm tra QR Operation hoặc tạo lại QR từ PO.'), 404
        if str(operation.get('po_status') or '').upper() != 'IN_PROGRESS':
            return jsonify(ok=False, error='PO_NOT_STARTED', error_code='PO-001', message=f"PO {operation.get('po_code') or ''} chưa Start hoặc đang tạm dừng", action='Nhờ quản đốc bấm Start/Tiếp tục PO trên màn hình quản lý.'), 409
        payload = dict(operation)
        # Setup is NOT a handover to some other screen -- the ESP terminal has
        # no room for one and its firmware is fixed, so the browser kiosk must
        # not invent a flow the real device cannot perform either. Setup is
        # done by scanning the SETUP label, exactly like any other Operation.
        # This only tells the worker WHICH label to go and scan; the actual
        # block lives in lock_startable_operation(), so a client that ignores
        # the hint still cannot start production.
        if payload.get('requires_setup') and not payload.get('setup_completed_at'):
            setup = fetch_one("""SELECT o.id,o.code,o.qr,o.expected_setup_minutes,
                    CASE WHEN strpos(upper(o.code),upper(p.code))>0 THEN o.code
                         ELSE p.code||'-'||o.code END display_key
                FROM operations o LEFT JOIN parts p ON p.id=o.part_id
                WHERE o.parent_operation_id=%s AND o.operation_type='SETUP'""", (payload['id'],))
            if setup:
                return jsonify(ok=False, error='SETUP_REQUIRED', error_code='OP-010',
                    operation=payload, setup_operation=dict(setup),
                    message=f"Cần setup máy trước. Quét QR {setup['display_key']}",
                    action='Làm theo tờ hướng dẫn setup tại máy, quét tem SETUP để bắt đầu.'), 409
        return jsonify(ok=True, type='operation', operation=payload)

    return jsonify(ok=False, error='UNSUPPORTED_QR', error_code='SCN-002', message='Sai định dạng QR', action='QR hợp lệ phải bắt đầu bằng WF|EMP|, WF|OP| hoặc WF|OPID|.'), 400


@bp.post('/api/kiosk-web/start')
@production_client_required
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
@production_client_required
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
