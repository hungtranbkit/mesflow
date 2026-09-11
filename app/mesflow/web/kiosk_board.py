"""Kiosk điều hành — dữ liệu cho màn hình lớn, chỉ đọc, gom theo MỘT PO.

VÌ SAO CÓ FILE NÀY. Bản v1 của màn hình lớn đọc thẳng ba endpoint sẵn có rồi
lọc ở trình duyệt. Cách đó hỏng theo đúng hai kiểu:

  * trộn task/KPI của nhiều PO lên một màn, người xem không biết con số đang
    nói về PO nào;
  * lọc sau khi server đã cắt theo `limit` -- cùng lỗi im lặng đã sửa ở
    REQ-PO-005, chỉ khác chỗ hiển thị.

Nên phạm vi PO phải nằm trong TRUY VẤN. File này KHÔNG viết lại quy tắc nghiệp
vụ nào: nó gọi đúng các repository/service đang chạy cho những màn khác
(DashboardRepository.daily_dashboard / production_control,
ProductionTraceService) rồi thu hẹp về PO đang xem. Mọi con số vì thế luôn khớp
với "Dashboard theo ngày" và với tháp điều khiển.

HAI ENDPOINT, HAI NHỊP. Tách ra vì chúng được hỏi ở hai tần suất khác nhau:

    GET /api/kiosk-board          -- KPI + task + chọn PO   (10-15 giây)
    GET /api/kiosk-board/activity -- dòng sự kiện sống       (3-5 giây)

Dòng sự kiện nhận `since_id` nên mỗi nhịp chỉ tải phần MỚI, không kéo lại cả
lịch sử. Mỗi sự kiện mang `id` ổn định của production_trace_events để phía
trình duyệt khử trùng lặp bằng id chứ không bằng thứ tự DOM.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from mesflow.db.connection import fetch_all, fetch_one
from mesflow.db.repositories.analytics import DashboardRepository
from mesflow.domain.policy import production_only_sql
from mesflow.web.auth import login_required
from mesflow.web.errors import api_error_response

bp = Blueprint('kiosk_board', __name__, url_prefix='/api')

PRODUCTION_ONLY_O = production_only_sql('o')

#: Số sự kiện giữ lại cho dòng "Hoạt động vừa xảy ra" của PO đang xem.
FOCUS_EVENT_LIMIT = 40
#: Số dòng tối đa cho vùng "Biến động PO khác" -- cố ý nhỏ để không chiếm màn.
OTHER_EVENT_LIMIT = 6
#: Trần số PO trong bộ chọn.
PO_OPTION_LIMIT = 40


def _int_arg(name: str, default=None):
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f'{name} phải là số nguyên') from None


def _po_options(limit: int = PO_OPTION_LIMIT) -> list[dict]:
    """Danh sách PO cho bộ chọn, PO đang có việc xếp trước.

    Thứ tự ưu tiên đúng như yêu cầu sản phẩm: đang có session mở -> có hoạt
    động gần đây -> còn lại. Xếp hạng tính trong SQL để bộ chọn không phụ thuộc
    vào việc trình duyệt đã tải được bao nhiêu.
    """
    return fetch_all(
        f"""SELECT po.id,po.code,po.product,po.status,po.planned_quantity,po.due_date,
              COALESCE(agg.open_sessions,0) open_sessions,
              COALESCE(agg.operation_count,0) operation_count,
              agg.last_activity_at
            FROM production_orders po
            LEFT JOIN (
              SELECT o.production_order_id po_id,
                COUNT(*) FILTER (WHERE {PRODUCTION_ONLY_O}) operation_count,
                COUNT(ws.id) FILTER (WHERE ws.status='OPEN') open_sessions,
                MAX(GREATEST(ws.started_at,COALESCE(ws.ended_at,ws.started_at))) last_activity_at
              FROM operations o LEFT JOIN work_sessions ws ON ws.operation_id=o.id
              GROUP BY o.production_order_id
            ) agg ON agg.po_id=po.id
            WHERE po.status IN ('RELEASED','IN_PROGRESS','PAUSED')
            ORDER BY (COALESCE(agg.open_sessions,0)>0) DESC,
                     agg.last_activity_at DESC NULLS LAST,
                     po.due_date ASC NULLS LAST, po.id DESC
            LIMIT %s""",
        (limit,))


def _resolve_po(po_id: int | None, options: list[dict]) -> dict | None:
    """PO đang xem: theo yêu cầu, nếu không thì PO đứng đầu bộ chọn.

    Kiosk v1 LUÔN có đúng một PO khi hệ thống còn PO khả dụng -- màn hình trống
    không nói gì cho người đứng xem.
    """
    if po_id is not None:
        row = fetch_one(
            """SELECT id,code,product,status,planned_quantity,due_date
               FROM production_orders WHERE id=%s""", (po_id,))
        if row:
            return dict(row)
        raise ValueError(f'Production Order #{po_id} không tồn tại')
    return dict(options[0]) if options else None


@bp.get('/kiosk-board')
@login_required
def kiosk_board():
    """KPI + task của MỘT PO, kèm bộ chọn PO. Chỉ đọc."""
    try:
        date = request.args.get('date') or None
        po_id = _int_arg('po_id')
        options = _po_options()
        po = _resolve_po(po_id, options)
        if po is None:
            return jsonify(ok=True, production_order=None, po_options=[],
                           kpis={}, tasks=[], date=date)

        day = DashboardRepository().daily_dashboard(date, limit=2000)
        focus_id = int(po['id'])
        # Thu hẹp về PO đang xem NGAY tại đây. Mọi panel phía sau chỉ đọc
        # `items`, nên không có đường nào để dữ liệu PO khác lọt vào.
        items = [dict(x) for x in (day.get('items') or [])
                 if int(x.get('po_id') or 0) == focus_id]
        sessions = [dict(x) for x in (day.get('sessions') or [])
                    if int(x.get('po_id') or 0) == focus_id]

        done = sum(int(x.get('day_good_qty') or 0) for x in items)
        defect = sum(int(x.get('day_defect_qty') or 0) for x in items)
        rework = sum(int(x.get('day_rework_qty') or 0) for x in items)
        open_sessions = sum(int(x.get('open_session_count') or 0) for x in items)
        workers = {int(w['employee_id']) for x in items
                   for w in (x.get('active_workers') or []) if w and w.get('employee_id')}

        return jsonify(ok=True,
                       date=day.get('context', {}).get('date') or date,
                       context=day.get('context', {}),
                       production_order=po,
                       po_options=[dict(x) for x in options],
                       kpis={
                           'day_good_qty': done,
                           'day_defect_qty': defect,
                           'day_rework_qty': rework,
                           'open_session_count': open_sessions,
                           'active_worker_count': len(workers),
                           'operation_count': len(items),
                           'planned_quantity': int(po.get('planned_quantity') or 0),
                       },
                       tasks=items,
                       sessions=sessions)
    except Exception as exc:  # noqa: BLE001
        return api_error_response(exc, logger_name=__name__)


#: Event nào đáng lên màn hình lớn. Cố ý là DANH SÁCH TRẮNG chứ không phải
#: "mọi thứ trừ vài loại": bảng production_trace_events còn phục vụ trang Truy
#: vết, nơi mọi event đều có ích. Màn hình lớn thì ngược lại -- thêm một loại
#: event ít giá trị là đẩy một sự kiện thật ra khỏi khung nhìn.
#:
#: Ánh xạ sang 5 nhóm chuyển động mà sản phẩm yêu cầu theo dõi. Loại nào backend
#: CHƯA sinh ra thì không có ở đây, và được ghi lại trong docs thay vì bịa.
FEED_EVENT_TYPES = (
    # employee nhận / bắt đầu việc
    'SESSION_STARTED',
    # employee trả / kết thúc việc
    'SESSION_FINISHED', 'SESSION_AUTO_CLOSED',
    # cập nhật sản lượng
    'GOOD_QUANTITY_RECORDED', 'DEFECT_QUANTITY_RECORDED', 'REPAIRABLE_DEFECT_RECORDED',
    # Operation / PO đổi trạng thái
    'OPERATION_STARTED', 'OPERATION_COMPLETED', 'OPERATION_STATUS_CHANGED',
    'PO_STARTED', 'PO_COMPLETED', 'PO_STATUS_CHANGED',
    # setup + sửa hàng
    'SETUP_COMPLETED', 'REWORK_RESOLVED',
    # chỉnh số liệu thủ công
    'VALUE_CHANGED',
)


def _feed_rows(*, po_id: int | None, exclude_po_id: int | None,
               since_id: int | None, limit: int) -> list[dict]:
    """Sự kiện thô cho dòng hoạt động, đã kèm tên Operation/PO để hiển thị.

    `since_id` là con trỏ TIẾN: mỗi nhịp poll chỉ lấy phần mới hơn id đã thấy.
    Sắp xếp theo (occurred_at, id) giảm dần rồi đảo ở nơi gọi, nên vẫn dùng
    được index idx_trace_po_time sẵn có.
    """
    where = ['t.event_type = ANY(%s)']
    params: list[object] = [list(FEED_EVENT_TYPES)]
    if po_id is not None:
        where.append('t.production_order_id=%s')
        params.append(po_id)
    if exclude_po_id is not None:
        where.append('(t.production_order_id IS NULL OR t.production_order_id<>%s)')
        params.append(exclude_po_id)
    if since_id is not None:
        where.append('t.id>%s')
        params.append(since_id)
    return fetch_all(
        f"""SELECT t.id,t.event_type,t.category,t.occurred_at,t.actor_name,t.actor_id,
              t.production_order_id,t.operation_id,t.session_id,t.title,t.description,
              t.quantity_delta,t.source,
              po.code po_code,o.code operation_code,o.name operation_name,
              o.done_qty operation_done_qty,COALESCE(pox.planned_quantity,0) operation_plan_qty
            FROM production_trace_events t
            LEFT JOIN production_orders po ON po.id=t.production_order_id
            LEFT JOIN operations o ON o.id=t.operation_id
            LEFT JOIN production_orders pox ON pox.id=o.production_order_id
            WHERE {' AND '.join(where)}
            ORDER BY t.occurred_at DESC,t.id DESC LIMIT %s""",
        (*params, limit))


def _serialize(row: dict) -> dict:
    """Một sự kiện đủ để câu hiển thị trả lời: AI · LÀM GÌ · TRÊN CÁI GÌ · RA SAO · LÚC NÀO.

    Câu chữ ghép ở trình duyệt; ở đây chỉ trả về các mảnh đã có thật trong dữ
    liệu. `actor_name` rỗng nghĩa là hệ thống tự làm (auto-close, reconcile) --
    trả về `actor_kind='SYSTEM'` để màn hình nói rõ "Hệ thống", không bịa ra một
    cái tên người.
    """
    actor = (row.get('actor_name') or '').strip()
    return {
        'id': int(row['id']),
        'event_type': row['event_type'],
        'category': row.get('category') or '',
        'occurred_at': row['occurred_at'].isoformat() if row.get('occurred_at') else None,
        'actor_name': actor,
        'actor_kind': 'PERSON' if actor else 'SYSTEM',
        'po_id': row.get('production_order_id'),
        'po_code': row.get('po_code') or '',
        'operation_id': row.get('operation_id'),
        'operation_code': row.get('operation_code') or '',
        'operation_name': row.get('operation_name') or '',
        'operation_done_qty': int(row.get('operation_done_qty') or 0),
        'operation_plan_qty': int(row.get('operation_plan_qty') or 0),
        'session_id': row.get('session_id'),
        'title': row.get('title') or '',
        'description': row.get('description') or '',
        'quantity_delta': row.get('quantity_delta'),
        'source': row.get('source') or 'NATIVE',
    }


@bp.get('/kiosk-board/activity')
@login_required
def kiosk_board_activity():
    """Dòng sự kiện sống: PO đang xem (chi tiết) + PO khác (tóm tắt).

    Trả về CẢ HAI trong một lượt để màn hình lớn chỉ cần một nhịp poll nhanh.
    Hai danh sách tách bạch từ phía server, nên sự kiện của PO khác không có
    đường nào chen vào danh sách của PO đang xem.
    """
    try:
        po_id = _int_arg('po_id')
        since_id = _int_arg('since_id')
        limit = min(max(_int_arg('limit', FOCUS_EVENT_LIMIT) or FOCUS_EVENT_LIMIT, 1), 200)
        if po_id is None:
            raise ValueError('po_id là bắt buộc')

        focus = [_serialize(r) for r in _feed_rows(
            po_id=po_id, exclude_po_id=None, since_id=since_id, limit=limit)]
        others = [_serialize(r) for r in _feed_rows(
            po_id=None, exclude_po_id=po_id, since_id=since_id, limit=OTHER_EVENT_LIMIT)]

        seen = [e['id'] for e in focus] + [e['id'] for e in others]
        return jsonify(ok=True,
                       po_id=po_id,
                       events=list(reversed(focus)),
                       other_events=list(reversed(others)),
                       latest_id=max(seen) if seen else since_id)
    except Exception as exc:  # noqa: BLE001
        return api_error_response(exc, logger_name=__name__)


@bp.get('/kiosk-board/po-options')
@login_required
def kiosk_board_po_options():
    """Danh sách PO cho bộ chọn, dùng chung cho Dashboard theo ngày và Kiosk.

    Tách riêng khỏi /api/kiosk-board vì Dashboard chỉ cần danh sách: gọi endpoint
    kia sẽ kéo theo cả một lượt gom dữ liệu ngày mà nó không dùng tới. Cùng một
    thứ tự ưu tiên ở cả hai màn, nên PO đứng đầu ở Dashboard cũng là PO đứng đầu
    ở Kiosk -- hai màn không được nói hai chuyện khác nhau về "PO nào đang chạy".
    """
    try:
        return jsonify(ok=True, items=[dict(x) for x in _po_options()])
    except Exception as exc:  # noqa: BLE001
        return api_error_response(exc, logger_name=__name__)
