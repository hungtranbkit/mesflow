from __future__ import annotations

import logging
import uuid

from psycopg.errors import DataError
from flask import Blueprint, jsonify, make_response, request, render_template

from mesflow import __version__
from mesflow.domain.qr_identity import (AmbiguousEmployeeQR, AmbiguousOperationQR,
                                        is_operation_qr, resolve_employee_id, resolve_operation_id)
from mesflow.domain.policy import STARTABLE_TYPES, type_in_sql
from mesflow.web.auth import (KIOSK_MOBILE_PERMISSION, kiosk_mobile_page_required,
                              kiosk_mobile_required, kiosk_public, login_required)
from mesflow.db.connection import fetch_one, fetch_all
from mesflow.db.repositories.execution import KioskRepository, WorkSessionRepository
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError
from mesflow.domain.errors import PermissionDeniedError

bp = Blueprint('web_kiosk', __name__)
logger = logging.getLogger(__name__)

# PUBLIC KIOSK SURFACE (business owner decision, 2026-09-12). Every route in
# this module is reachable by a workshop machine that has never logged in and
# has no session cookie: /kiosk and /kiosk/employee-productivity render
# directly, and scan/start/finish carry @kiosk_public (see web/auth.py for the
# full boundary rationale). Operator identity comes from the scanned employee
# badge, never from a web account. The ONE exception is /api/kiosk-web/demo-
# data below, which stays @login_required because it dumps badge QR values.

# Danh sách việc trên kiosk chỉ được chứa loại Operation MỞ ĐƯỢC session.
# lock_startable_operation() từ chối bàn SỬA HÀNG, nên liệt kê nó ở đây là đưa
# cho công nhân một dòng việc mà chính máy sẽ từ chối khi họ chọn -- đúng lỗi
# danh mục QR đã sửa từ trước bằng cùng tập này (xem master_data.qr_labels).
STARTABLE_ONLY_O = type_in_sql(STARTABLE_TYPES, 'o')


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
    if isinstance(exc, DataError):
        # Số vượt khỏi kiểu cột (good_qty = 2**31) là lỗi dữ liệu vào, không
        # phải lỗi hệ thống -- nhưng vẫn phải ghi lại, vì nó cũng có thể là dấu
        # hiệu một thiết bị đang gửi rác.
        logger.warning('Kiosk data error: %s', exc)
        return jsonify(ok=False, error='INVALID_REQUEST', error_code='REQ-400',
                       message='Dữ liệu nhập không đúng định dạng hoặc vượt giới hạn.',
                       action='Kiểm tra lại số lượng vừa nhập rồi thử lại.'), 400
    if isinstance(exc, (ValueError, RepositoryError)):
        return jsonify(ok=False, error='INVALID_REQUEST', error_code='REQ-400', message=message,
                       action='Quét lại đúng thứ tự hoặc nhập lại dữ liệu.'), 400
    # KeyError/TypeError CỐ Ý KHÔNG nằm ở nhánh 400 nữa. Chúng là LỖI LẬP TRÌNH,
    # không phải lỗi của người quét, và việc xếp chúng vào 400 gây ra hai hậu
    # quả đo được trên 71.0.0.310:
    #   * nội dung ngoại lệ Python lọt ra cho người gọi ẨN DANH trên internet --
    #     POST /api/kiosk-web/start {} trả về message "'employee_id'";
    #     {"employee_id":"abc"} trả về "invalid literal for int() with base 10";
    #     và người đứng máy thì đọc được một câu Python thay vì một hướng dẫn.
    #   * tệ hơn: lỗi thật BIẾN MẤT. action_logging chỉ ghi error_traces khi
    #     status>=500 hoặc có exception chưa bắt; 400 nên sau cả ba lời gọi trên
    #     `SELECT count(*) FROM error_traces` = 0 và outcome là 'FAILED' chứ
    #     không phải 'ERROR'. Một defect thật không bao giờ tới được màn Nhật ký
    #     lỗi mà cả System Console dựng lên để theo dõi.
    # Nay chúng rơi xuống nhánh 500 bên dưới: câu trả lời cho người dùng là câu
    # chung (không lộ nội bộ), còn traceback thì được GHI LẠI.
    logger.exception('Kiosk request failed: %s', request.path)
    return jsonify(ok=False, error='INTERNAL_ERROR', error_code='SYS-500',
                   message='Máy chủ không xử lý được yêu cầu.',
                   action='Ghi lại mã SYS-500 và báo người quản trị.'), 500


#: Các trường của nhân viên được phép ra khỏi MẶT QUÉT CÔNG KHAI. Danh sách
#: cho phép, không phải danh sách cấm: thêm cột mới vào bảng employees sẽ không
#: âm thầm đẩy nó ra internet.
PUBLIC_EMPLOYEE_FIELDS = ('id', 'employee_no', 'name', 'department', 'position', 'active')


def _public_employee(row):
    return {k: row[k] for k in PUBLIC_EMPLOYEE_FIELDS if k in row}


def _normalize_qr(value: object) -> str:
    return str(value or '').strip()


def _never_cache(response):
    """Trang/khai báo phiên bản KHÔNG được nằm lại trong cache.

    Mọi asset của kiosk đã gắn `?v=<version>` (xem kiosk.html), nên trình duyệt
    tự lấy bản mới sau một lần deploy -- NHƯNG chỉ khi nó đọc được tài liệu HTML
    mới, vì chính tài liệu đó mang các con trỏ `?v=`. Trang kiosk trước đây trả
    về không kèm một header cache nào, nên nó rơi vào phép đoán tự do của trình
    duyệt/proxy (heuristic freshness). Một bản HTML cũ nằm lại là kiosk vĩnh
    viễn nạp đúng bộ JS/CSS cũ, dù đã deploy bao nhiêu lần -- và vì `?v=` trong
    đó cũng cũ, không có gì trên đời buộc nó phải tải lại.

    Máy ở xưởng bị khoá bàn phím và không ai với tới được, nên đây không phải
    chuyện tối ưu mà là chuyện bản vá có tới được máy hay không.
    """
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@bp.get('/kiosk')
def kiosk_page():
    return _never_cache(make_response(render_template(
        'kiosk.html', version=__version__,
        api_base='/api/kiosk-web',
        manifest_url='/kiosk.webmanifest',
        mobile=False)))


# --------------------------------------------------------------------------
# MOBILE KIOSK -- SAME BUSINESS FLOW, ITS OWN URL AND ITS OWN AUTH POLICY
# --------------------------------------------------------------------------
# Why a second URL instead of a flag on /kiosk: /kiosk must stay open (a
# workshop machine has no account and no cookie -- see the module header), and
# a phone must not. Those are two different policies, and a policy that
# depends on which mode a page happens to be in is not a policy. Two routes
# make the difference something you can read off the URL map, test in
# isolation, and put in an nginx rule if it ever needs one.
#
# Why NOT User-Agent sniffing: a User-Agent is free text the caller chooses.
# It is a hint for LAYOUT, never a gate. Nothing here reads it, and
# tests/test_kiosk_mobile_route_boundary.py fails the build if that changes.
#
# The template, the JS, the CSS and every business rule are the SAME files as
# /kiosk. Only two things differ, both passed in as template variables: the
# API prefix the page calls, and the manifest it installs from.
@bp.get('/kiosk-mobile')
@kiosk_mobile_page_required
def kiosk_mobile_page():
    return _never_cache(make_response(render_template(
        'kiosk.html', version=__version__,
        api_base='/api/kiosk-mobile',
        manifest_url='/kiosk-mobile.webmanifest',
        mobile=True)))


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
#: PWA ở mức tối thiểu, CỐ Ý.
#:
#: Đủ để iPhone "Thêm vào màn hình chính" mở ra toàn màn hình, không hơn. KHÔNG
#: có service worker: kiosk đã có cơ chế tự nạp lại khi máy chủ lên phiên bản
#: mới (heartbeat so `data-version` của tab với phiên bản máy chủ -- xem
#: kiosk.js). Một service worker phục vụ trang từ cache sẽ đánh nhau với đúng
#: cơ chế đó và có thể giữ một máy ở phiên bản cũ mà không ai biết. Trang
#: kiosk phải luôn là bản máy chủ đang chạy.
KIOSK_MANIFEST = {
    'name': 'KIMEX Kiosk — Trạm thao tác',
    'short_name': 'KIMEX Kiosk',
    'description': 'Trạm thao tác: quét thẻ nhân viên và công đoạn bằng máy quét.',
    'start_url': '/kiosk',
    'scope': '/kiosk',
    'display': 'standalone',
    'orientation': 'any',
    'background_color': '#f3f5f7',
    'theme_color': '#102b3f',
    'lang': 'vi',
    'icons': [
        {'src': '/static/kiosk-icon.svg', 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'},
    ],
}


# Riêng cho điện thoại: cùng biểu tượng, nhưng start_url/scope phải trỏ về
# /kiosk-mobile. Dùng chung một manifest thì cú "Thêm vào màn hình chính" trên
# iPhone mở ra /kiosk -- tức trang CÔNG KHAI, không phải trang đã đăng nhập.
KIOSK_MOBILE_MANIFEST = dict(
    KIOSK_MANIFEST,
    name='KIMEX Kiosk — Điện thoại',
    short_name='Kiosk ĐT',
    description='Quét QR nhân viên và công đoạn bằng camera điện thoại.',
    start_url='/kiosk-mobile',
    scope='/kiosk-mobile',
)


@bp.get('/kiosk.webmanifest')
def kiosk_manifest():
    response = jsonify(KIOSK_MANIFEST)
    response.headers['Content-Type'] = 'application/manifest+json'
    return response


@bp.get('/kiosk-mobile.webmanifest')
def kiosk_mobile_manifest():
    response = jsonify(KIOSK_MOBILE_MANIFEST)
    response.headers['Content-Type'] = 'application/manifest+json'
    return response


@bp.get('/kiosk/employee-productivity')
def employee_productivity_wallboard_page():
    return render_template('wallboard_employee_productivity.html', version=__version__)


@bp.get('/api/kiosk-web/health')
def kiosk_health():
    # Khai báo phiên bản NHẸ, không đụng DB: dùng để đối chiếu bản đang chạy
    # trên máy chủ với bản một tab kiosk đã nạp. no-store là bắt buộc -- một
    # phản hồi phiên bản nằm lại trong cache thì nói mãi một con số cũ, tức là
    # nói dối đúng về thứ nó tồn tại để trả lời.
    return _never_cache(jsonify(ok=True, version=__version__, module='web-kiosk'))


@bp.post('/api/kiosk-web/heartbeat')
def kiosk_web_heartbeat():
    return _heartbeat_response()


def _heartbeat_response():
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
    return _demo_data_response()


def _demo_data_response():
    try:
        employees = fetch_all(
            """SELECT id, employee_no, name, department, position, qr
               FROM employees
               WHERE active=TRUE
               ORDER BY employee_no, name
               LIMIT 300"""
        )
        operations = fetch_all(
            f"""SELECT o.id,o.code,o.name,o.qr,o.status,COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,
                      p.code part_code,p.name part_name,po.code po_code,po.product
               FROM operations o
               LEFT JOIN parts p ON p.id=o.part_id
               LEFT JOIN production_orders po ON po.id=o.production_order_id
               WHERE UPPER(TRIM(COALESCE(po.status,'')))='IN_PROGRESS'
                 AND UPPER(TRIM(COALESCE(o.status,''))) NOT IN ('COMPLETED','CANCELLED')
                 AND {STARTABLE_ONLY_O}
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
@kiosk_public
def kiosk_scan():
    return _scan_response()


def _scan_response():
    body = request.get_json(silent=True) or {}
    qr = _normalize_qr(body.get('qr'))
    if not qr:
        return jsonify(ok=False, error='QR_REQUIRED', error_code='SCN-001', message='Chưa nhận được mã quét', action='Kiểm tra nguồn và dây máy quét, rồi quét lại.'), 400

    if qr.upper().startswith('WF|EMP|'):
        # Cùng lý do như nhánh Operation bên dưới: LIMIT 1 ở đây từng ĐOÁN khi
        # một chuỗi khớp hai nhân viên, và cái giá là công của cả ca ghi sang
        # tên người khác.
        try:
            employee_id = resolve_employee_id(qr)
        except AmbiguousEmployeeQR as exc:
            return jsonify(ok=False, error='AMBIGUOUS_QR', error_code='EMP-002',
                           message=str(exc),
                           action='Sửa mã QR của các nhân viên bị trùng trong Danh mục rồi in lại thẻ.'), 409
        except NotFoundError:
            employee_id = None
        employee = fetch_one(
            """SELECT id,employee_no,name,department,position,active,employment_status,qr
               FROM employees WHERE id=%s""",
            (employee_id,),
        ) if employee_id else None
        if not employee or not employee['active']:
            # Cùng lý do như PO-001 bên dưới: thẻ đã đọc ra ĐÚNG một người thì
            # nói tên người đó ra, kể cả khi họ đã nghỉ. "Không tìm thấy nhân
            # viên đang hoạt động" mà không kèm tên buộc quản đốc phải đi tra
            # tay xem tấm thẻ trên tay công nhân là của ai.
            return jsonify(
                ok=False, error='EMPLOYEE_NOT_FOUND', error_code='EMP-001',
                message='Không tìm thấy nhân viên đang hoạt động',
                action='Quét đúng thẻ nhân viên hoặc nhờ quản đốc kiểm tra trạng thái nhân viên.',
                **({'scanned': {'kind': 'employee', 'title': employee['name'] or '',
                                'sub': employee['employee_no'] or ''}} if employee else {}),
            ), 404
        # TẤT CẢ session đang mở, không phải một. Từ migration 0054 một người
        # được giữ nhiều session OPEN trên các Operation khác nhau (trông 2-3
        # máy cùng lúc). `LIMIT 1` cũ sẽ lặng lẽ giấu đi những việc còn lại --
        # đúng kiểu sai nguy hiểm nhất ở màn hình xưởng: người đứng máy tin rằng
        # mình chỉ còn một việc đang chạy.
        #
        # ORDER BY s.id DESC giữ NGUYÊN thứ tự cũ, nên phần tử đầu tiên vẫn đúng
        # là dòng mà `LIMIT 1` từng trả về -- điều kiện để `open_session` bên
        # dưới tương thích ngược từng bit với client cũ.
        opened_rows = fetch_all(
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
               ORDER BY s.id DESC""",
            (employee['id'],),
        )
        opened = opened_rows[0] if opened_rows else None
        # KHÔNG TRẢ LẠI MÃ THẺ. Chuỗi `employees.qr` là một THÔNG TIN XÁC THỰC --
        # chính vì thế /api/kiosk-web/demo-data bị khoá lại sau sự cố
        # 2026-09-09 ("dumps ... every badge QR value, which is a credential").
        # Nhưng mặt quét này ẩn danh và chấp nhận cả `employee_no`, nên trước
        # bản vá bất kỳ ai cũng dò được NV001, NV002... và thu về đúng chuỗi thẻ
        # của từng người. Đo được trên 71.0.0.310: quét "WF|EMP|NV002" (đoán,
        # chưa hề cầm thẻ) trả về qr + họ tên.
        # Trạm quét KHÔNG cần chuỗi này: nó vừa tự đọc được từ tấm thẻ trên tay.
        # `employment_status` cũng bỏ vì cùng lý do -- không màn hình nào dùng.
        # `open_session` (số ít) GIỮ NGUYÊN: firmware ESP và mọi client dựng
        # trước 0054 đọc đúng trường này. Thêm `open_sessions` bên cạnh chứ
        # không thay thế -- client cũ tiếp tục thấy một session như trước, client
        # mới đọc đủ danh sách. Đây là lý do không đổi tên trường cũ.
        return jsonify(ok=True, type='employee',
                       employee=_public_employee(employee),
                       open_session=dict(opened) if opened else None,
                       open_sessions=[dict(x) for x in opened_rows])

    # Two payload shapes, one code path. `WF|OP|<code>` is what the labels
    # already printed in the workshop carry; `WF|OPID|<id>` is what new labels
    # (every SETUP label included) carry, because an Operation code is only
    # unique within its Part and so cannot be a durable identifier.
    if is_operation_qr(qr):
        # Trước đây chỗ này tự giải mã và kết thúc bằng LIMIT 1 -- tức là ĐOÁN
        # khi một mã trùng ở nhiều Part. Nay dùng resolver chung, nó từ chối ca
        # mơ hồ thay vì lấy đại một dòng (xem domain/qr_identity.py).
        try:
            operation_id = resolve_operation_id(qr)
        except AmbiguousOperationQR as exc:
            # Không để lọt ra trình xử lý lỗi chung của Flask: ở đó nó thành
            # HTTP 500 INTERNAL_ERROR không có error_code, và kiosk.js không
            # tra được câu hướng dẫn nào -- màn hình xưởng chỉ hiện "Hệ thống
            # gặp lỗi", đúng lúc thứ cần nói là "in lại tem".
            return jsonify(ok=False, error='AMBIGUOUS_QR', error_code='OP-002',
                           message=str(exc),
                           action='In lại tem QR cho Operation này (tem mới dùng mã theo id), '
                                  'hoặc chọn Operation trên màn hình quản lý.'), 409
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
               WHERE o.id=%s""",
            (operation_id,),
        )
        if not operation:
            return jsonify(ok=False, error='OPERATION_NOT_FOUND', error_code='OP-001', message='Không tìm thấy Operation', action='Kiểm tra QR Operation hoặc tạo lại QR từ PO.'), 404
        if str(operation.get('po_status') or '').upper() != 'IN_PROGRESS':
            # LUẬT NGHIỆP VỤ TỪ CHỐI KHÔNG ĐƯỢC XOÁ KẾT QUẢ ĐỌC MÃ.
            #
            # Máy ĐÃ đọc ra tem này là Operation nào -- `operation` ngay trên
            # đây là bằng chứng. Trả về mỗi câu "PO chưa Start" là vứt đi đúng
            # thứ người cầm điện thoại cần để biết mình quét trúng tem nào, và
            # để đối chiếu tem in có đúng không. `scanned` mang lại đúng phần
            # đã nhận diện được, KHÔNG mở thêm dữ liệu nào: tên + mã hiển thị
            # của chính Operation vừa quét, ba trường, không có id, không có
            # sản lượng, không có gì mà một lần quét thành công không trả về.
            #
            # Bổ sung THÊM trường, không đổi trường cũ: ok/error/error_code/
            # message/action giữ nguyên từng chữ, nên mọi client cũ (ESP v2,
            # trạm cố định, bài kiểm cũ) không thấy khác biệt nào.
            return jsonify(
                ok=False, error='PO_NOT_STARTED', error_code='PO-001',
                message=f"PO {operation.get('po_code') or ''} chưa Start hoặc đang tạm dừng",
                action='Nhờ quản đốc bấm Start/Tiếp tục PO trên màn hình quản lý.',
                scanned={
                    'kind': 'operation',
                    'title': operation.get('name') or '',
                    'sub': operation.get('display_key') or operation.get('code') or '',
                },
            ), 409
        payload = dict(operation)
        # A linked SETUP row is informational, never a gate: it says this
        # Operation has related setup work, not that setup must happen first.
        # The 409 that used to live here (and the SETUP_REQUIRED / OP-010 error
        # it raised) was removed on 2026-09-09 -- production is never blocked
        # by setup state, so the scan simply succeeds.
        return jsonify(ok=True, type='operation', operation=payload)

    return jsonify(ok=False, error='UNSUPPORTED_QR', error_code='SCN-002', message='Sai định dạng QR', action='QR hợp lệ phải bắt đầu bằng WF|EMP|, WF|OP| hoặc WF|OPID|.'), 400


@bp.post('/api/kiosk-web/start')
@kiosk_public
def kiosk_start():
    return _start_response()


def _required_id(body, field, label_vi):
    """Một id bắt buộc, đọc thành lỗi NGƯỜI ĐỌC ĐƯỢC nếu thiếu hoặc sai kiểu.

    Trước bản vá, `int(body['employee_id'])` để KeyError/TypeError tự nổ và
    `_error()` xếp chúng vào 400 kèm nguyên văn ngoại lệ Python -- người đứng
    máy nhận được "'employee_id'" hoặc "invalid literal for int() with base 10:
    'abc'". Nay chúng là lỗi lập trình đi vào nhánh 500 (và được GHI LẠI), nên
    phần "thiếu trường" phải được kiểm tường minh ở đây, nếu không một yêu cầu
    thiếu trường sẽ thành 500 -- đúng kiểu đánh đổi sai.
    """
    value = body.get(field)
    if value in (None, ''):
        raise ValueError(f'Thiếu {label_vi}. Quét lại từ đầu.')
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label_vi} không hợp lệ ({value!r}). Quét lại từ đầu.')


def _start_response():
    body = request.get_json(silent=True) or {}
    try:
        payload = {
            'request_id': str(body.get('request_id') or f'WEB-START-{uuid.uuid4()}'),
            'employee_id': _required_id(body, 'employee_id', 'mã nhân viên'),
            'operation_id': _required_id(body, 'operation_id', 'mã công đoạn'),
            'station_id': int(body['station_id']) if body.get('station_id') else None,
            'device_uuid': str(body.get('device_uuid') or 'WEB-KIOSK'),
        }
        return jsonify(WorkSessionRepository().start(payload)), 201
    except Exception as exc:
        return _error(exc)


@bp.post('/api/kiosk-web/finish/<int:session_id>')
@kiosk_public
def kiosk_finish(session_id: int):
    return _finish_response(session_id)


def _finish_response(session_id: int):
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


# --------------------------------------------------------------------------
# /api/kiosk-mobile/* -- the phone's own front door
# --------------------------------------------------------------------------
# ONE implementation, TWO doors with different locks. Each route below is a
# two-line wrapper around the exact same _*_response() function the public
# /api/kiosk-web/* routes call, so there is no second copy of a business rule,
# a validation, an error code or an idempotency key to drift out of sync --
# only the decorator differs, which is the entire point.
#
# The gate is @kiosk_mobile_required (signed-in session + kiosk.view), on the
# SERVER. Hiding a button in the phone's JavaScript protects nothing: an
# unauthenticated POST straight at this URL is the case that has to fail, and
# these decorators are what makes it fail.
@bp.get('/api/kiosk-mobile/health')
def kiosk_mobile_health():
    # Deliberately open, exactly like /api/kiosk-web/health: it returns a
    # version string and nothing else, and a health probe that needs a login
    # is not a health probe.
    return jsonify(ok=True, version=__version__, module='mobile-kiosk',
                   permission=KIOSK_MOBILE_PERMISSION)


@bp.post('/api/kiosk-mobile/heartbeat')
@kiosk_mobile_required
def kiosk_mobile_heartbeat():
    return _heartbeat_response()


@bp.get('/api/kiosk-mobile/demo-data')
@kiosk_mobile_required
def kiosk_mobile_demo_data():
    return _demo_data_response()


@bp.post('/api/kiosk-mobile/scan')
@kiosk_mobile_required
def kiosk_mobile_scan():
    return _scan_response()


@bp.post('/api/kiosk-mobile/start')
@kiosk_mobile_required
def kiosk_mobile_start():
    return _start_response()


@bp.post('/api/kiosk-mobile/finish/<int:session_id>')
@kiosk_mobile_required
def kiosk_mobile_finish(session_id: int):
    return _finish_response(session_id)
