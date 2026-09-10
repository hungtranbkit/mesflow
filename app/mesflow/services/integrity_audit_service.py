"""Read-only database invariant auditor.

Backs `mesflow audit-integrity` (cli.py). Every query here is a plain
SELECT -- this module never writes anything, by design (see Gate 3 of the
2026-08-26 Reliability Validation Round 2 request: "Never auto-repair").

This complements session_audit_service.audit() (which is about *staleness*
-- sessions that should have been closed by now) with checks about
*correctness* -- rows that should never exist at all if every write path
and DB constraint behaved. Most of these are defense-in-depth: the
condition is already supposed to be impossible (a CHECK constraint, a FK,
a partial UNIQUE index), and a non-empty category here means that
assumption broke somewhere -- a raw SQL fix during an incident, a
constraint dropped by a bad migration, a partially-restored backup, or a
genuine application bug. Intended to be run after every chaos/load/soak
phase, per the same request's rule: "After every chaos/load phase run:
audit-sessions / audit-integrity."
"""
from __future__ import annotations
from mesflow.domain.policy import support_only_sql

from typing import Any

from mesflow.db.connection import fetch_all

# Bộ lọc loại Operation lấy từ mesflow.domain.policy -- KHÔNG chép lại chuỗi
# COALESCE(...) ở từng câu truy vấn. Trước 2026-09-10 mỗi module tự viết một
# bản, và mỗi lần quên một chỗ là một lần sản lượng của OP phụ lọt vào tiến độ
# PO, hoặc PO không bao giờ đạt COMPLETED.
SUPPORT_ONLY_O = support_only_sql('o')



def _status_ended_at_mismatch() -> list[dict[str, Any]]:
    # Invariant: CLOSED <=> ended_at IS NOT NULL (this holds both directions
    # -- an OPEN session must never carry a stale ended_at either, which
    # would be just as confusing to any code that branches on one field but
    # displays the other).
    return fetch_all("""
        SELECT id,employee_id,operation_id,status,started_at,ended_at
        FROM work_sessions
        WHERE (status='CLOSED' AND ended_at IS NULL) OR (status='OPEN' AND ended_at IS NOT NULL)
        ORDER BY id""")


def _negative_quantity() -> list[dict[str, Any]]:
    # rework_qty already has a DB CHECK constraint (rework_qty>=0 AND
    # rework_qty<=defect_qty, migration 0022); good_qty/defect_qty do not --
    # this is the only thing standing between a bad code path and a
    # negative quantity silently corrupting every report built on top of
    # these columns.
    return fetch_all("""
        SELECT id,employee_id,operation_id,status,good_qty,defect_qty,rework_qty
        FROM work_sessions
        WHERE good_qty<0 OR defect_qty<0 OR rework_qty<0 OR rework_qty>defect_qty
        ORDER BY id""")


def _ended_before_started() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT id,employee_id,operation_id,started_at,ended_at,status
        FROM work_sessions WHERE ended_at IS NOT NULL AND ended_at<started_at
        ORDER BY started_at""")


def _multiple_open_per_employee() -> list[dict[str, Any]]:
    # Defense check for uq_open_session_per_employee (migration 0003: a
    # partial UNIQUE index on work_sessions(employee_id) WHERE
    # status='OPEN'). Should always be empty by construction; a non-empty
    # result means that index was dropped, bypassed by a raw write, or
    # never actually applied against this database.
    return fetch_all("""
        SELECT employee_id,COUNT(*) open_count,array_agg(id ORDER BY id) session_ids
        FROM work_sessions WHERE status='OPEN'
        GROUP BY employee_id HAVING COUNT(*)>1
        ORDER BY employee_id""")


def _orphan_employee() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN employees e ON e.id=ws.employee_id
        WHERE e.id IS NULL ORDER BY ws.id""")


def _orphan_operation() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN operations o ON o.id=ws.operation_id
        WHERE o.id IS NULL ORDER BY ws.id""")


def _orphan_part_or_po() -> list[dict[str, Any]]:
    # operations.part_id/production_order_id both carry FK CASCADE -- an
    # orphan here would mean a part/PO was deleted without cascading
    # correctly, which would then make every session on that operation
    # reference production context that no longer exists.
    return fetch_all("""
        SELECT o.id operation_id,o.production_order_id,o.part_id
        FROM operations o
        LEFT JOIN production_orders po ON po.id=o.production_order_id
        LEFT JOIN parts p ON p.id=o.part_id
        WHERE po.id IS NULL OR p.id IS NULL
        ORDER BY o.id""")


def _duplicate_close_event() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT session_id,COUNT(*) close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_FINISHED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")


def _duplicate_auto_close_event() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT session_id,COUNT(*) auto_close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_AUTO_CLOSED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")


def _auto_close_changed_quantity() -> list[dict[str, Any]]:
    # Invariant: AUTO_SHIFT_END must never fake/change quantity -- a
    # SESSION_AUTO_CLOSED trace event should only ever touch status/ended_at,
    # never carry a non-null quantity_delta. auto_close_for_shift_end()
    # itself never sets good_qty/defect_qty, but this checks the actual
    # emitted event, not just the code's intent -- catches a regression
    # that started attaching a quantity_delta to that event type.
    return fetch_all("""
        SELECT id,session_id,quantity_delta,occurred_at
        FROM production_trace_events
        WHERE event_type='SESSION_AUTO_CLOSED' AND quantity_delta IS NOT NULL AND quantity_delta<>0
        ORDER BY id""")


def _duplicate_quantity_movement() -> list[dict[str, Any]]:
    # Invariant: quantity movements don't duplicate one logical event --
    # a movement carrying a non-empty correlation_id should never appear
    # more than once for the same session/type/delta under that
    # correlation_id (the standard idempotency-key shape used elsewhere in
    # this codebase, e.g. kiosk_idempotency.request_id).
    return fetch_all("""
        SELECT correlation_id,session_id,movement_type,delta,COUNT(*) occurrence_count,array_agg(id ORDER BY id) movement_ids
        FROM quantity_movements
        WHERE correlation_id<>''
        GROUP BY correlation_id,session_id,movement_type,delta HAVING COUNT(*)>1
        ORDER BY correlation_id""")


def _duplicate_offline_event() -> list[dict[str, Any]]:
    # Defense check for kiosk_client_events.client_event_id's UNIQUE
    # constraint (migration 0023) -- offline replay dedup depends entirely
    # on that constraint; this is the same "verify the assumption, don't
    # just trust it" pattern as _multiple_open_per_employee().
    return fetch_all("""
        SELECT client_event_id,COUNT(*) occurrence_count,array_agg(id ORDER BY id) event_ids
        FROM kiosk_client_events
        GROUP BY client_event_id HAVING COUNT(*)>1
        ORDER BY client_event_id""")


def _closed_session_operation_still_completed_conflict() -> list[dict[str, Any]]:
    # Invariant: Operation/PO state compatible with work-session state --
    # an Operation already marked COMPLETED should not have a session still
    # OPEN against it (this is also surfaced live as the
    # OPERATION_COMPLETED_SESSION_OPEN exception in exception_service.py;
    # checking it here too means the raw data condition is caught even if
    # the exception detector's reconcile() didn't run or was disabled).
    return fetch_all("""
        SELECT ws.id session_id,ws.employee_id,ws.operation_id,o.status operation_status,ws.started_at
        FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
        WHERE ws.status='OPEN' AND o.status='COMPLETED'
        ORDER BY ws.id""")


def _inactive_kiosk_with_live_status() -> list[dict[str, Any]]:
    # Invariant: a DISABLED/PENDING kiosk identity can't become ACTIVE via
    # execution -- heartbeat()/execution requests already gate on
    # status='ACTIVE' (see KioskRepository.heartbeat() and
    # _legacy_kiosk_identity()), so a DISABLED/PENDING identity with a
    # *recent* kiosk_status heartbeat would mean that gate was bypassed
    # somewhere. A stale heartbeat from before the identity was disabled is
    # expected and not flagged -- only one within the last 24h, i.e. one
    # that could only have happened after whatever disabled it.
    return fetch_all("""
        SELECT ki.id identity_id,ki.device_uuid,ki.status identity_status,ks.last_heartbeat_at
        FROM kiosk_identities ki JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
        WHERE ki.status IN ('DISABLED','PENDING') AND ks.last_heartbeat_at>CURRENT_TIMESTAMP-INTERVAL '24 hours'
        ORDER BY ki.id""")


# --- Kiểm tra bổ sung 2026-09-09 -----------------------------------------
#
# Sáu bất biến bên dưới sinh ra từ audit kiến trúc. Điểm chung của chúng: khi
# vi phạm, hệ thống KHÔNG báo lỗi -- số chỉ đơn giản là sai, hoặc dữ liệu chỉ
# đơn giản là không hiện ra. Đó là lý do chúng cần một lệnh đối soát chủ động
# chứ không thể trông vào việc người dùng phát hiện.


def _support_operation_with_production_quantity() -> list[dict[str, Any]]:
    """OP hỗ trợ (SETUP / SỬA HÀNG) mang sản lượng.

    Theo policy, OP hỗ trợ ghi nhận CÔNG chứ không ghi nhận sản lượng. Một
    dòng ở đây nghĩa là sản lượng đã bị ghi vào chỗ không đường nào cộng nó
    vào tiến độ PO -- số đó biến mất khỏi mọi báo cáo mà không có dấu vết.
    """
    return fetch_all(f"""SELECT o.id operation_id,o.code,o.operation_type,
            o.done_qty,o.defect_qty,o.rework_qty,po.code po_code
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        WHERE {SUPPORT_ONLY_O}
          AND (COALESCE(o.done_qty,0)>0 OR COALESCE(o.defect_qty,0)>0 OR COALESCE(o.rework_qty,0)>0)
        ORDER BY o.id""")


def _consumption_target_mismatch() -> list[dict[str, Any]]:
    """Dòng vật tư trỏ về Operation KHÁC với Operation của session.

    Bất biến (1) của operation_input_consumptions. Vi phạm nghĩa là sản lượng
    đếm cho một OP còn nguyên liệu trừ của OP khác -- hai bên sổ nói hai
    chuyện. Nguồn cũ: transfer_operation() không đổi ledger theo session.
    """
    return fetch_all("""SELECT c.session_id,c.target_operation_id,ws.operation_id session_operation_id
        FROM operation_input_consumptions c JOIN work_sessions ws ON ws.id=c.session_id
        WHERE c.target_operation_id<>ws.operation_id ORDER BY c.session_id""")


def _consumption_held_by_non_reporting_session() -> list[dict[str, Any]]:
    """Session không tính vào báo cáo mà vẫn giữ đầu vào.

    Bất biến (2). Session bị loại khỏi báo cáo hoặc chưa đóng thì không đóng
    góp gì, nên không được chiếm sản lượng của OP nguồn. Vi phạm chặn OP đích
    khác lấy đúng số hàng đó -- im lặng, không có thông báo nào.
    """
    return fetch_all("""SELECT c.session_id,c.source_operation_id,ws.status,
            ws.excluded_from_reports
        FROM operation_input_consumptions c JOIN work_sessions ws ON ws.id=c.session_id
        WHERE ws.excluded_from_reports=TRUE OR ws.status<>'CLOSED'
        ORDER BY c.session_id""")


def _rework_ledger_does_not_balance() -> list[dict[str, Any]]:
    """Tổng ở rework_ledger không khớp số cộng dồn trên session nguồn.

    rework_ledger là bản ghi bất biến từng lần xử lý; work_sessions chỉ là số
    cộng dồn. Lệch nhau nghĩa là một lệnh sửa số liệu đã ghi đè lên phần đã
    ghi sổ, và sản phẩm đã sửa có thể quay lại hàng chờ để được credit lần hai.
    """
    return fetch_all("""SELECT ws.id session_id,ws.rework_qty,ws.scrap_qty,
            l.reworked ledger_reworked,l.scrapped ledger_scrapped
        FROM work_sessions ws
        JOIN (SELECT source_session_id,SUM(qty_reworked) reworked,SUM(qty_scrapped) scrapped
              FROM rework_ledger GROUP BY source_session_id) l ON l.source_session_id=ws.id
        WHERE ws.rework_qty<l.reworked OR ws.scrap_qty<l.scrapped
        ORDER BY ws.id""")


def _quantity_shape_violates_check() -> list[dict[str, Any]]:
    """rework + phế vượt quá NG trên cùng một session.

    CSDL có CHECK cho việc này, nên một dòng ở đây nghĩa là constraint đã bị
    gỡ hoặc dữ liệu vào bằng đường không qua ứng dụng.
    """
    return fetch_all("""SELECT id session_id,good_qty,defect_qty,rework_qty,scrap_qty
        FROM work_sessions
        WHERE COALESCE(rework_qty,0)+COALESCE(scrap_qty,0)>COALESCE(defect_qty,0)
        ORDER BY id""")


def _ambiguous_operation_qr() -> list[dict[str, Any]]:
    """Tem cũ `WF|OP|<mã>` hiện đang trỏ tới NHIỀU HƠN MỘT Operation.

    Bản trước của hàm này gom nhóm theo `upper(code) HAVING COUNT(*)>1`, tức
    là đi tìm hai Operation cùng mã. `operations_code_key` cấm đúng điều đó,
    nên câu ấy KHÔNG BAO GIỜ trả về dòng nào: một bộ dò luôn luôn im lặng, và
    sự im lặng đó bị đọc thành "sạch".

    Sự mơ hồ CÓ THẬT nằm ở chỗ khác, và nó chéo cột chứ không cùng cột:
    resolver nhận một payload khi nó khớp `operations.qr` HOẶC
    `operations.code`. Hai cột đó unique riêng lẻ nhưng không unique chéo
    nhau, nên chuỗi 'WF|OP|CUT' có thể vừa là `qr` của hàng A (đã đổi mã, tem
    cũ giữ nguyên -- cố ý) vừa là `code` của hàng B. Lúc đó cả A và B đều
    không quét được bằng tem cũ.

    Chỉ đọc. Việc cần làm cho mỗi dòng là in lại tem cho hàng được nêu.
    """
    return fetch_all("""SELECT a.id qr_owner_id,a.code qr_owner_code,a.qr payload,
            b.id code_owner_id,b.code code_owner_code
        FROM operations a JOIN operations b
          ON b.id<>a.id AND upper(b.code)=upper(substring(a.qr from 7))
        WHERE upper(a.qr) LIKE 'WF|OP|%' AND upper(a.qr) NOT LIKE 'WF|OPID|%'
        ORDER BY a.id""")


def _ambiguous_employee_badge() -> list[dict[str, Any]]:
    """Một chuỗi thẻ trỏ tới nhiều nhân viên.

    Cùng hình dạng lỗi như trên, và hậu quả nặng hơn: công của cả một ca ghi
    sang tên người khác. `employee_no` và `qr` unique riêng lẻ, không unique
    chéo nhau.
    """
    return fetch_all("""SELECT a.id qr_owner_id,a.employee_no qr_owner_no,a.qr payload,
            b.id no_owner_id,b.employee_no no_owner_no
        FROM employees a JOIN employees b
          ON b.id<>a.id AND upper(b.employee_no)=upper(substring(a.qr from 8))
        WHERE a.active AND b.active AND upper(a.qr) LIKE 'WF|EMP|%'
        ORDER BY a.id""")


def _duplicate_display_key_in_part() -> list[dict[str, Any]]:
    """Hai Operation trong CÙNG một Part hiện ra giống hệt nhau trên màn hình.

    Mã lưu trong bảng vẫn khác nhau (unique toàn cục lo việc đó), nhưng thứ
    người dùng đọc là display key `<part>-<mã>`. Hai dòng cùng display key
    trong một Part nghĩa là không ai ở xưởng phân biệt được chúng -- kể cả khi
    hệ thống thì phân biệt được.
    """
    return fetch_all("""SELECT o.production_order_id,o.part_id,p.code part_code,
            upper(CASE WHEN strpos(upper(o.code),upper(p.code))>0 THEN o.code
                       ELSE p.code||'-'||o.code END) display_key,
            COUNT(*) n,array_agg(o.id ORDER BY o.id) operation_ids
        FROM operations o JOIN parts p ON p.id=o.part_id
        GROUP BY o.production_order_id,o.part_id,p.code,4
        HAVING COUNT(*)>1 ORDER BY 5 DESC""")


def _material_source_unresolved() -> list[dict[str, Any]]:
    """Bật dòng vật tư nhưng không có OP nguồn nào được nối.

    Xảy ra khi Template khai `input_source_code` mà lúc tạo PO không giải ra
    được. Operation này sẽ không bao giờ ghi được ledger đầu vào.
    """
    return fetch_all("""SELECT o.id operation_id,o.code,p.code part_code,po.code po_code
        FROM operations o JOIN parts p ON p.id=o.part_id
        JOIN production_orders po ON po.id=o.production_order_id
        WHERE o.input_flow_enabled=TRUE AND o.input_source_operation_id IS NULL
        ORDER BY o.id""")


def _material_source_outside_its_po() -> list[dict[str, Any]]:
    """OP nguồn nằm ở PO khác -- ledger sẽ trừ hàng của một PO không liên quan."""
    return fetch_all("""SELECT o.id operation_id,o.code,po.code po_code,
            src.id source_operation_id,src.code source_code,spo.code source_po_code
        FROM operations o JOIN operations src ON src.id=o.input_source_operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        JOIN production_orders spo ON spo.id=src.production_order_id
        WHERE o.production_order_id<>src.production_order_id ORDER BY o.id""")


def _setup_parent_wrong_scope() -> list[dict[str, Any]]:
    """OP SETUP treo vào một OP cha ở Part/PO khác.

    Liên kết đi bằng parent_operation_id nên nó không thể trỏ vào hư không,
    nhưng nó VẪN có thể trỏ sang Part khác -- và khi đó thời gian setup được
    tính cho sai chỗ.
    """
    return fetch_all("""SELECT s.id setup_id,s.code setup_code,s.part_id setup_part_id,
            pa.id parent_id,pa.code parent_code,pa.part_id parent_part_id
        FROM operations s JOIN operations pa ON pa.id=s.parent_operation_id
        WHERE COALESCE(s.operation_type,'PRODUCTION')='SETUP'
          AND (s.part_id<>pa.part_id OR s.production_order_id<>pa.production_order_id)
        ORDER BY s.id""")


def _rework_bench_duplicated() -> list[dict[str, Any]]:
    """Nhiều hơn một bàn SỬA HÀNG cho cùng một (PO, Part).

    Đường tạo lấy bàn cũ theo (PO, Part, loại) rồi `ORDER BY id LIMIT 1`, nên
    khi có hai bàn thì một nửa số lượng sửa chạy vào bàn này, nửa kia vào bàn
    kia, và không tổng nào đúng. Không có unique index nào cấm điều này.
    """
    return fetch_all("""SELECT production_order_id,part_id,COUNT(*) n,
            array_agg(id ORDER BY id) operation_ids
        FROM operations WHERE COALESCE(operation_type,'PRODUCTION')='REWORK'
        GROUP BY production_order_id,part_id HAVING COUNT(*)>1 ORDER BY 3 DESC""")


def _rework_ledger_operation_mismatch() -> list[dict[str, Any]]:
    """Dòng ledger sửa hàng trỏ tới Operation không khớp session của chính nó."""
    return fetch_all("""SELECT rl.id ledger_id,rl.source_session_id,rl.source_operation_id,
            ws.operation_id session_operation_id
        FROM rework_ledger rl JOIN work_sessions ws ON ws.id=rl.source_session_id
        WHERE ws.operation_id<>rl.source_operation_id ORDER BY rl.id""")


def _offline_events_ambiguous() -> list[dict[str, Any]]:
    """Sự kiện offline đang bị giữ vì tem của nó mơ hồ.

    Tách riêng khỏi OFFLINE_EVENTS_STUCK: những cái này không chờ một điều
    kiện nghiệp vụ đúng lại theo thời gian, chúng chờ một người in lại tem.
    """
    return fetch_all("""SELECT client_event_id,kiosk_id,event_type,reason_code,reason,received_at
        FROM kiosk_client_events
        WHERE reason_code IN ('AMBIGUOUS_OPERATION_QR','AMBIGUOUS_EMPLOYEE_QR')
          AND status <> 'accepted'
        ORDER BY received_at""")


def _offline_events_stuck() -> list[dict[str, Any]]:
    """Sự kiện kiosk offline kẹt ở retryable quá lâu.

    Không phải lỗi tự thân -- nhưng một sự kiện kẹt nhiều ngày nghĩa là điều
    kiện nghiệp vụ của nó không bao giờ đúng, và công của ca đó đang treo.
    """
    return fetch_all("""SELECT client_event_id,kiosk_id,event_type,attempt_count,
            reason_code,reason,received_at
        FROM kiosk_client_events
        WHERE status='retryable' AND received_at < CURRENT_TIMESTAMP - INTERVAL '1 day'
        ORDER BY received_at""")


def audit_integrity() -> dict[str, list[dict[str, Any]]]:
    """Run every invariant check and return {category: [violations]}.

    Read-only. An empty list for a category means that invariant held
    across every row checked; it does not mean the category was skipped."""
    return {
        'STATUS_ENDED_AT_MISMATCH': _status_ended_at_mismatch(),
        'NEGATIVE_QUANTITY': _negative_quantity(),
        'ENDED_BEFORE_STARTED': _ended_before_started(),
        'MULTIPLE_OPEN_PER_EMPLOYEE': _multiple_open_per_employee(),
        'ORPHAN_EMPLOYEE': _orphan_employee(),
        'ORPHAN_OPERATION': _orphan_operation(),
        'ORPHAN_PART_OR_PO': _orphan_part_or_po(),
        'DUPLICATE_CLOSE_EVENT': _duplicate_close_event(),
        'DUPLICATE_AUTO_CLOSE_EVENT': _duplicate_auto_close_event(),
        'AUTO_CLOSE_CHANGED_QUANTITY': _auto_close_changed_quantity(),
        'DUPLICATE_QUANTITY_MOVEMENT': _duplicate_quantity_movement(),
        'DUPLICATE_OFFLINE_EVENT': _duplicate_offline_event(),
        'OPERATION_COMPLETED_SESSION_STILL_OPEN': _closed_session_operation_still_completed_conflict(),
        'INACTIVE_KIOSK_WITH_LIVE_STATUS': _inactive_kiosk_with_live_status(),
        # Bổ sung 2026-09-09 -- xem chú thích của từng hàm.
        'SUPPORT_OP_WITH_PRODUCTION_QUANTITY': _support_operation_with_production_quantity(),
        'CONSUMPTION_TARGET_MISMATCH': _consumption_target_mismatch(),
        'CONSUMPTION_HELD_BY_NON_REPORTING_SESSION': _consumption_held_by_non_reporting_session(),
        'REWORK_LEDGER_DOES_NOT_BALANCE': _rework_ledger_does_not_balance(),
        'QUANTITY_SHAPE_VIOLATES_CHECK': _quantity_shape_violates_check(),
        'AMBIGUOUS_OPERATION_QR': _ambiguous_operation_qr(),
        'AMBIGUOUS_EMPLOYEE_BADGE': _ambiguous_employee_badge(),
        'DUPLICATE_DISPLAY_KEY_IN_PART': _duplicate_display_key_in_part(),
        'MATERIAL_SOURCE_UNRESOLVED': _material_source_unresolved(),
        'MATERIAL_SOURCE_OUTSIDE_ITS_PO': _material_source_outside_its_po(),
        'SETUP_PARENT_WRONG_SCOPE': _setup_parent_wrong_scope(),
        'REWORK_BENCH_DUPLICATED': _rework_bench_duplicated(),
        'REWORK_LEDGER_OPERATION_MISMATCH': _rework_ledger_operation_mismatch(),
        'OFFLINE_EVENTS_STUCK': _offline_events_stuck(),
        'OFFLINE_EVENTS_AMBIGUOUS': _offline_events_ambiguous(),
    }
