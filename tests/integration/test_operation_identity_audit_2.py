"""Danh tính của một Operation là gì, và điều gì xảy ra khi mã của nó trùng hoặc đổi.

Đây là bản kiểm chứng bằng CHẠY THẬT cho đợt audit danh tính Operation lần hai
(2026-09-10). Mọi khẳng định trong báo cáo audit phải có một bài ở đây dựng lại
được, vì grep không phân biệt được "chỗ này dùng mã" với "chỗ này dùng mã và vì
thế sai".

Bốn khái niệm bị lẫn lộn, tách ra như sau:

  * DANH TÍNH BẤT BIẾN là ``operations.id``. Khoá ngoại, session, ledger vật
    tư, event, tem QR mới -- tất cả trỏ vào nó.
  * KHOÁ NGHIỆP VỤ / HIỂN THỊ là ``operations.code``, và trên màn hình là
    display key ``<part>-<code>``.
  * UNIQUE Ở DB, tính đến bản này, vẫn là TOÀN CỤC trên ``code`` (và trên
    ``qr``) -- không phải theo Part. test_db_uniqueness_is_still_global ghi lại
    đúng trạng thái đó; nó là bài test tài liệu hoá, và phải đỏ vào ngày ai đó
    chuyển sang unique theo (part_id, code), để bản báo cáo được cập nhật cùng
    lúc với schema.
  * RESOLVER QR ưu tiên ``WF|OPID|<id>``, chấp nhận ``WF|OP|<mã>`` cũ, và TỪ
    CHỐI khi mã cũ giải ra nhiều hơn một Operation.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

pytestmark = pytest.mark.postgres

OPID_PREFIX = 'WF|OPID|'


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


def _po(cur, code: str, qty: int = 100) -> int:
    cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
        VALUES(%s,'SP',%s,'IN_PROGRESS') RETURNING id""", (code, qty))
    return cur.fetchone()['id']


def _part(cur, po_id: int, code: str, sort_order: int = 0) -> int:
    cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
        VALUES(%s,%s,%s,%s,true) RETURNING id""", (po_id, code, code, sort_order))
    return cur.fetchone()['id']


def _op(cur, po_id: int, part_id: int, code: str, *, qr: str | None = None,
        done: int = 0, sort_order: int = 0) -> int:
    cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,done_qty)
        VALUES(%s,%s,%s,%s,'PLANNED',%s,%s,%s) RETURNING id""",
        (po_id, part_id, code, code, qr if qr is not None else f'WF|OP|{code}', sort_order, done))
    return cur.fetchone()['id']


def _employee(cur, no: str) -> int:
    cur.execute("""INSERT INTO employees(employee_no,name,active,qr)
        VALUES(%s,'Nhân viên',true,%s) RETURNING id""", (no, f'WF|EMP|{no}'))
    return cur.fetchone()['id']


def _session(cur, employee_id: int, operation_id: int, request_id: str, good: int = 0) -> int:
    """Một Session đã đóng, đặt LÙI XA trong quá khứ.

    Các bài ở đây chỉ cần Session tồn tại như một liên kết theo id (lịch sử
    production của Operation). Nếu đặt vào hôm nay thì sản lượng của nó cộng
    vào bảng tổng hợp theo ngày, và những bài khác trong bộ test khẳng định
    tổng đó -- tests/integration/test_rework_overview_rollup.py đã đỏ đúng như
    vậy (98 -> 150, chính bằng 10+42 của hai bài dưới đây). Lùi 45 ngày thì
    liên kết vẫn nguyên mà không bài nào khác nhìn thấy.
    """
    cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,started_at,ended_at,status,
            good_qty,defect_qty,start_request_id)
        VALUES(%s,%s,CURRENT_TIMESTAMP-INTERVAL '45 day',CURRENT_TIMESTAMP-INTERVAL '45 day'+INTERVAL '1 hour',
            'CLOSED',%s,0,%s) RETURNING id""", (employee_id, operation_id, good, request_id))
    return cur.fetchone()['id']


def _new_template(conn, code: str) -> int:
    return conn.execute(
        "INSERT INTO templates(code,name,product,version,active) VALUES(%s,'T','SP','1.0',true) RETURNING id",
        (code,)).fetchone()['id']


# ---------------------------------------------------------------- C. DB uniqueness

def test_db_uniqueness_is_still_global_not_per_part(db):
    """PO1/PartA có CUT, PO1/PartB cũng muốn CUT -- và DB không cho.

    Đây là câu trả lời cho "uniqueness hiện đang enforce ở mức nào": TOÀN CỤC.
    Ý định nghiệp vụ (một mã OP được phép lặp giữa các Part) CHƯA đạt ở lớp
    schema; nó đang được mô phỏng ở lớp ứng dụng bằng cách gấp mã Part vào mã
    Operation lúc tạo PO (xem bài kế tiếp).
    """
    sfx = _suffix()
    with db.cursor() as cur:
        po = _po(cur, f'PO-UQ-{sfx}')
        part_a = _part(cur, po, 'PARTA', 0)
        part_b = _part(cur, po, 'PARTB', 1)
        _op(cur, po, part_a, f'CUT-{sfx}')
        with pytest.raises(psycopg.errors.UniqueViolation) as exc:
            _op(cur, po, part_b, f'CUT-{sfx}', qr=f'WF|OP|CUT-B-{sfx}')
    assert 'operations_code_key' in str(exc.value)

    # Và không có unique theo (part_id, code) nào đứng cạnh nó.
    with db.cursor() as cur:
        cur.execute("""SELECT indexdef FROM pg_indexes
            WHERE tablename='operations' AND indexdef ILIKE '%unique%'""")
        defs = [r['indexdef'] for r in cur.fetchall()]
    code_indexes = [d for d in defs if '(code)' in d.replace(' ', '')]
    assert code_indexes, f'không còn unique nào trên operations.code: {defs}'
    assert all('part_id' not in d for d in code_indexes), (
        'Đã có unique theo Part cho operations.code -- cập nhật báo cáo audit '
        f'và bài test này: {code_indexes}')


def test_code_fold_is_what_makes_two_parts_able_to_share_one_op_code(db):
    """Cơ chế tương đương hiện tại: gấp mã Part vào mã Operation lúc instantiate.

    Nghiệp vụ nói "PartA và PartB đều có OP CUT". Cái thực sự nằm trong bảng là
    ``<PO>-PARTA-CUT`` và ``<PO>-PARTB-CUT``: hai mã KHÁC NHAU. Người dùng thấy
    display key đúng như mong đợi, nên ở màn hình thì đạt -- nhưng mã lưu trong
    DB không phải mã họ gõ, và mọi thứ đọc ``operations.code`` như một mã
    nghiệp vụ (ví dụ cột operation_id của file Excel) đang đọc mã đã gấp.
    """
    from mesflow.db.connection import transaction, fetch_all
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-FOLD-{sfx}')
    repo = TemplateTreeRepository()
    repo.replace_tree(template_id, {
        'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0},
                  {'key': 'b', 'code': 'PARTB', 'name': 'B', 'sort_order': 1}],
        'operations': [{'part_key': 'a', 'code': 'CUT', 'name': 'Cắt A', 'sort_order': 0},
                       {'part_key': 'b', 'code': 'CUT', 'name': 'Cắt B', 'sort_order': 0}],
        'equipment': []})
    out = repo.instantiate(template_id, code=f'PO-FOLD-{sfx}', planned_quantity=10)

    rows = fetch_all("""SELECT o.id,o.code,p.code part_code FROM operations o
        JOIN parts p ON p.id=o.part_id WHERE o.production_order_id=%s ORDER BY p.sort_order""",
        (out['production_order_id'],))
    assert len(rows) == 2
    assert rows[0]['id'] != rows[1]['id'], 'hai Part phải cho hai Operation riêng'
    assert [r['code'] for r in rows] == [f'PO-FOLD-{sfx}-PARTA-CUT', f'PO-FOLD-{sfx}-PARTB-CUT']
    # Mã người dùng gõ ('CUT') không phải mã được lưu: đó chính là khoảng cách
    # còn lại giữa ý định nghiệp vụ và schema.
    assert not any(r['code'] == 'CUT' for r in rows)


# ---------------------------------------------------------------- Rename

def test_renaming_a_code_breaks_no_id_based_link(db):
    """Đổi mã sau khi đã có session, ledger vật tư, OP nguồn và event kiosk.

    Mọi liên kết nội bộ đi bằng id, nên đổi mã không được làm đứt cái nào.
    """
    from mesflow.db.connection import fetch_one
    from mesflow.domain.qr_identity import resolve_operation_id

    sfx = _suffix()
    with db.cursor() as cur:
        po = _po(cur, f'PO-RN-{sfx}')
        part = _part(cur, po, f'P-{sfx}')
        source_id = _op(cur, po, part, f'SRC-{sfx}', done=50, sort_order=0)
        target_id = _op(cur, po, part, f'TGT-{sfx}', sort_order=1)
        cur.execute("""UPDATE operations SET input_flow_enabled=true,input_source_operation_id=%s
            WHERE id=%s""", (source_id, target_id))
        emp = _employee(cur, f'E{sfx}'[:12])
        session_id = _session(cur, emp, target_id, f'REQ-{sfx}', good=10)
        cur.execute("""INSERT INTO operation_input_consumptions(source_operation_id,target_operation_id,
                session_id,good_qty_consumed,defect_qty_consumed)
            VALUES(%s,%s,%s,10,0)""", (source_id, target_id, session_id))
        cur.execute("""INSERT INTO kiosk_events(event_uuid,device_uuid,event_type,severity,message,operation_id)
            VALUES(%s,'DEV','SCAN_OPERATION','INFO','quét',%s)""", (f'EVT-{sfx}', source_id))

        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'SRC-RENAMED-{sfx}', source_id))

        cur.execute("SELECT input_source_operation_id FROM operations WHERE id=%s", (target_id,))
        assert cur.fetchone()['input_source_operation_id'] == source_id
        cur.execute("""SELECT source_operation_id,target_operation_id FROM operation_input_consumptions
            WHERE session_id=%s""", (session_id,))
        ledger = cur.fetchone()
        assert (ledger['source_operation_id'], ledger['target_operation_id']) == (source_id, target_id)
        cur.execute("SELECT operation_id FROM work_sessions WHERE id=%s", (session_id,))
        assert cur.fetchone()['operation_id'] == target_id
        cur.execute("SELECT operation_id FROM kiosk_events WHERE event_uuid=%s", (f'EVT-{sfx}',))
        assert cur.fetchone()['operation_id'] == source_id

    # Tem đã in vẫn quét được: qr KHÔNG bị viết lại khi đổi mã, đó là chủ ý.
    assert resolve_operation_id(f'WF|OP|SRC-{sfx}') == source_id
    assert resolve_operation_id(f'{OPID_PREFIX}{source_id}') == source_id
    assert fetch_one('SELECT code FROM operations WHERE id=%s', (source_id,))['code'] == f'SRC-RENAMED-{sfx}'


# ---------------------------------------------------------------- QR resolver

def test_id_based_qr_resolves_exactly_and_never_needs_context(db):
    from mesflow.domain.qr_identity import resolve_operation_id

    sfx = _suffix()
    with db.cursor() as cur:
        po = _po(cur, f'PO-ID-{sfx}')
        part = _part(cur, po, f'P-{sfx}')
        op_id = _op(cur, po, part, f'OP-{sfx}')
        cur.execute('UPDATE operations SET qr=%s WHERE id=%s', (f'{OPID_PREFIX}{op_id}', op_id))
    assert resolve_operation_id(f'{OPID_PREFIX}{op_id}') == op_id
    # Ngữ cảnh chỉ THU HẸP, không bao giờ đổi câu trả lời cho một tem theo id.
    assert resolve_operation_id(f'{OPID_PREFIX}{op_id}', part_id=999999) == op_id


def test_legacy_qr_matching_two_operations_is_refused_not_guessed(db):
    """Tem cũ mơ hồ -> lỗi nói rõ, không phải LIMIT 1.

    Dựng lại đúng đường vào có thật: đổi tên mã để lại `qr` cũ đòi mã đó, rồi
    mã ấy được cấp cho một Operation khác.
    """
    from mesflow.db.connection import execute
    from mesflow.db.repositories.base import ConflictError
    from mesflow.domain.qr_identity import resolve_operation_id

    sfx = _suffix()
    code = f'CUT-{sfx}'
    with db.cursor() as cur:
        po = _po(cur, f'PO-AMB-{sfx}')
        part_a = _part(cur, po, 'PARTA', 0)
        part_b = _part(cur, po, 'PARTB', 1)
        old_id = _op(cur, po, part_a, code)
        # Đổi tên: qr giữ nguyên 'WF|OP|<code>' (chủ ý -- tem đã in ngoài xưởng).
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{code}-OLD', old_id))
        new_id = _op(cur, po, part_b, code, qr=f'{OPID_PREFIX}PENDING-{sfx}')
    execute('UPDATE operations SET qr=%s WHERE id=%s', (f'{OPID_PREFIX}{new_id}', new_id))

    with pytest.raises(ConflictError) as exc:
        resolve_operation_id(f'WF|OP|{code}')
    message = str(exc.value)
    assert code in message and 'In lại tem' in message
    # Cả hai vẫn giải được tuyệt đối bằng id -- sự mơ hồ chỉ thuộc về tem cũ.
    assert resolve_operation_id(f'{OPID_PREFIX}{old_id}') == old_id
    assert resolve_operation_id(f'{OPID_PREFIX}{new_id}') == new_id


def test_a_code_still_claimed_by_an_old_label_cannot_be_reassigned(db):
    """Chặn ở đầu vào, để ca mơ hồ ở bài trên không xảy ra qua đường ứng dụng."""
    from mesflow.db.repositories.base import ConflictError
    from mesflow.db.repositories.master_data import OperationRepository

    sfx = _suffix()
    code = f'CUT-{sfx}'
    with db.cursor() as cur:
        po = _po(cur, f'PO-CLAIM-{sfx}')
        part_a = _part(cur, po, 'PARTA', 0)
        part_b = _part(cur, po, 'PARTB', 1)
        old_id = _op(cur, po, part_a, code)
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{code}-OLD', old_id))
        other_id = _op(cur, po, part_b, f'OTHER-{sfx}')

    with pytest.raises(ConflictError) as exc:
        OperationRepository().update(other_id, {'code': code})
    assert 'tem QR cũ' in str(exc.value)

    with pytest.raises(ConflictError):
        OperationRepository().create({'production_order_id': po, 'part_id': part_b,
                                      'code': code, 'name': 'Mới'})


# ---------------------------------------------------------------- Template / clone

def test_a_valid_multi_part_template_is_not_reported_as_a_cycle(db):
    """Chu trình GIẢ: ba hàng riêng biệt, không có vòng nào, vẫn bị chặn.

        PartA: OP01 (không nguồn), OP02 (nguồn OP01)
        PartB: OP01 (nguồn OP02)

    Bản cũ khoá đồ thị theo mã TRẦN, nên PartB/OP01 ghi đè PartA/OP01 và hai
    cạnh gộp lại thành ``{OP01: [OP02], OP02: [OP01]}``. Kết quả:
    "Dependency cycle: OP01 -> OP02 -> OP01", chặn cả việc lưu Template lẫn
    việc tạo PO -- tức là chặn đúng thứ mà việc scope mã theo Part sinh ra để
    cho phép.
    """
    from mesflow.db.connection import transaction, fetch_all
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-NOCYC-{sfx}')
    repo = TemplateTreeRepository()
    repo.replace_tree(template_id, {
        'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0},
                  {'key': 'b', 'code': 'PARTB', 'name': 'B', 'sort_order': 1}],
        'operations': [
            {'part_key': 'a', 'code': 'OP01', 'name': 'A1', 'sort_order': 0},
            {'part_key': 'a', 'code': 'OP02', 'name': 'A2', 'sort_order': 1,
             'input_flow_enabled': True, 'input_source_code': 'OP01'},
            {'part_key': 'b', 'code': 'OP01', 'name': 'B1', 'sort_order': 0,
             'input_flow_enabled': True, 'input_source_code': 'OP02'}],
        'equipment': []})
    out = repo.instantiate(template_id, code=f'PO-NOCYC-{sfx}', planned_quantity=10)

    rows = fetch_all("""SELECT p.code part,o.code,srcp.code src_part,src.code src_code
        FROM operations o JOIN parts p ON p.id=o.part_id
        LEFT JOIN operations src ON src.id=o.input_source_operation_id
        LEFT JOIN parts srcp ON srcp.id=src.part_id
        WHERE o.production_order_id=%s ORDER BY p.sort_order,o.sort_order""",
        (out['production_order_id'],))
    links = {(r['part'], r['code'].rsplit('-', 1)[-1]): (r['src_part'], r['src_code']) for r in rows}
    # OP02 của PartA lấy từ OP01 của chính PartA -- cùng Part thì không mơ hồ.
    assert links[('PARTA', 'OP02')] == ('PARTA', f'PO-NOCYC-{sfx}-PARTA-OP01')
    # OP01 của PartB trỏ chéo Part sang OP02 -- mã đó chỉ có ở đúng một Part.
    assert links[('PARTB', 'OP01')] == ('PARTA', f'PO-NOCYC-{sfx}-PARTA-OP02')


def test_duplicate_op_codes_across_parts_link_within_their_own_part(db):
    """Mỗi Part nối OP nguồn trong chính Part của mình, không nối chéo."""
    from mesflow.db.connection import transaction, fetch_all
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-DUP-{sfx}')
    repo = TemplateTreeRepository()
    repo.replace_tree(template_id, {
        'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0},
                  {'key': 'b', 'code': 'PARTB', 'name': 'B', 'sort_order': 1}],
        'operations': [
            {'part_key': 'a', 'code': 'OP01', 'name': 'A1', 'sort_order': 0},
            {'part_key': 'a', 'code': 'OP02', 'name': 'A2', 'sort_order': 1,
             'input_flow_enabled': True, 'input_source_code': 'OP01'},
            {'part_key': 'b', 'code': 'OP01', 'name': 'B1', 'sort_order': 0},
            {'part_key': 'b', 'code': 'OP02', 'name': 'B2', 'sort_order': 1,
             'input_flow_enabled': True, 'input_source_code': 'OP01'}],
        'equipment': []})
    out = repo.instantiate(template_id, code=f'PO-DUP-{sfx}', planned_quantity=10)

    rows = fetch_all("""SELECT p.code part,o.code,srcp.code src_part
        FROM operations o JOIN parts p ON p.id=o.part_id
        LEFT JOIN operations src ON src.id=o.input_source_operation_id
        LEFT JOIN parts srcp ON srcp.id=src.part_id
        WHERE o.production_order_id=%s ORDER BY p.sort_order,o.sort_order""",
        (out['production_order_id'],))
    by_part = {(r['part'], r['code'].rsplit('-', 1)[-1]): r for r in rows}
    assert by_part[('PARTA', 'OP02')]['src_part'] == 'PARTA'
    assert by_part[('PARTB', 'OP02')]['src_part'] == 'PARTB', (
        'OP02 của PartB lấy đầu vào từ OP01 của Part khác -- nối chéo Part')


def test_an_input_source_code_present_in_two_parts_is_refused(db):
    """Mơ hồ = lỗi tường minh, không phải "lấy Part đầu tiên".

    Bản cũ chọn im lặng Part đầu theo thứ tự sort. PO tạo ra trông bình thường,
    còn mọi session sau đó ghi ledger vào OP nguồn của Part khác -- và guard
    phân bổ lại chặn không cho sửa.
    """
    from mesflow.db.connection import transaction
    from mesflow.db.repositories.base import ConflictError
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-AMB-{sfx}')
    with pytest.raises(ConflictError) as exc:
        TemplateTreeRepository().replace_tree(template_id, {
            'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0},
                      {'key': 'b', 'code': 'PARTB', 'name': 'B', 'sort_order': 1},
                      {'key': 'c', 'code': 'PARTC', 'name': 'C', 'sort_order': 2}],
            'operations': [
                {'part_key': 'a', 'code': 'CUT', 'name': 'Cắt A', 'sort_order': 0},
                {'part_key': 'c', 'code': 'CUT', 'name': 'Cắt C', 'sort_order': 0},
                {'part_key': 'b', 'code': 'DRILL', 'name': 'Khoan B', 'sort_order': 0,
                 'input_flow_enabled': True, 'input_source_code': 'CUT'}],
            'equipment': []})
    message = str(exc.value)
    assert 'PARTA' in message and 'PARTC' in message


def test_a_cross_part_source_with_exactly_one_match_still_works(db):
    """Template cũ trỏ chéo Part vẫn chạy -- chỉ ca MƠ HỒ bị chặn."""
    from mesflow.db.connection import transaction, fetch_all
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-X-{sfx}')
    repo = TemplateTreeRepository()
    repo.replace_tree(template_id, {
        'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0},
                  {'key': 'b', 'code': 'PARTB', 'name': 'B', 'sort_order': 1}],
        'operations': [{'part_key': 'a', 'code': 'CUT', 'name': 'Cắt', 'sort_order': 0},
                       {'part_key': 'b', 'code': 'WELD', 'name': 'Hàn', 'sort_order': 0,
                        'input_flow_enabled': True, 'input_source_code': 'CUT'}],
        'equipment': []})
    out = repo.instantiate(template_id, code=f'PO-X-{sfx}', planned_quantity=10)
    rows = fetch_all("""SELECT p.code part,srcp.code src_part FROM operations o
        JOIN parts p ON p.id=o.part_id
        LEFT JOIN operations src ON src.id=o.input_source_operation_id
        LEFT JOIN parts srcp ON srcp.id=src.part_id
        WHERE o.production_order_id=%s ORDER BY p.sort_order""", (out['production_order_id'],))
    assert rows[1]['src_part'] == 'PARTA'


def test_a_real_cycle_inside_one_part_is_still_rejected(db):
    from mesflow.db.connection import transaction
    from mesflow.db.repositories.base import ConflictError
    from mesflow.db.repositories.master_data import TemplateTreeRepository

    sfx = _suffix()
    with transaction() as conn:
        template_id = _new_template(conn, f'TPL-CYC-{sfx}')
    with pytest.raises((ConflictError, ValueError)) as exc:
        TemplateTreeRepository().replace_tree(template_id, {
            'parts': [{'key': 'a', 'code': 'PARTA', 'name': 'A', 'sort_order': 0}],
            'operations': [
                {'part_key': 'a', 'code': 'X', 'name': 'X', 'sort_order': 0,
                 'input_flow_enabled': True, 'input_source_code': 'Y'},
                {'part_key': 'a', 'code': 'Y', 'name': 'Y', 'sort_order': 1,
                 'input_flow_enabled': True, 'input_source_code': 'X'}],
            'equipment': []})
    assert 'Dependency cycle' in str(exc.value)


# ---------------------------------------------------------------- Excel roundtrip

def test_excel_import_will_not_move_an_operation_into_another_po(db, api):
    """Một dòng Excel không được kéo một Operation đã có sản lượng sang PO khác.

    Bản cũ tra ``WHERE UPPER(code)=?`` không kèm PO rồi UPDATE cả
    production_order_id: 42 SP và một Session đã đóng chuyển từ PO-ONE sang
    PO-TWO, API trả về {"ok":true,"updated":1}.
    """
    import io
    import os
    from openpyxl import Workbook

    sfx = _suffix()
    code = f'SHARED-{sfx}'
    with db.cursor() as cur:
        po_one = _po(cur, f'PO-ONE-{sfx}')
        part_one = _part(cur, po_one, 'PONE')
        po_two = _po(cur, f'PO-TWO-{sfx}')
        _part(cur, po_two, 'PTWO')
        op_id = _op(cur, po_one, part_one, code, done=42)
        emp = _employee(cur, f'X{sfx}'[:12])
        _session(cur, emp, op_id, f'REQ-{sfx}', good=42)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Operations'
    sheet.append(['operation_id', 'product', 'po', 'part', 'part_order', 'operation_name',
                  'drawing', 'plan', 'done', 'defect', 'status', 'qr'])
    sheet.append([code, 'SP', f'PO-TWO-{sfx}', 'Part TWO', 0, 'Công đoạn 1', '',
                  100, 0, 0, 'PLANNED', f'WF|OP|{code}'])
    buf = io.BytesIO()
    workbook.save(buf)
    buf.seek(0)

    base = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')
    response = api.post(f'{base}/api/operations/import',
        files={'file': ('ops.xlsx', buf,
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
        data={'mode': 'merge'}, timeout=30)
    assert response.status_code >= 400, (
        f'import phải bị từ chối, nhận {response.status_code}: {response.text[:300]}')
    assert f'PO-ONE-{sfx}' in response.text

    with db.cursor() as cur:
        cur.execute("""SELECT po.code po_code,o.done_qty,
                (SELECT COUNT(*) FROM work_sessions ws WHERE ws.operation_id=o.id) sessions
            FROM operations o JOIN production_orders po ON po.id=o.production_order_id
            WHERE o.id=%s""", (op_id,))
        row = cur.fetchone()
    assert row['po_code'] == f'PO-ONE-{sfx}', 'Operation đã bị chuyển sang PO khác'
    assert row['done_qty'] == 42 and row['sessions'] == 1


def test_excel_import_can_still_move_an_operation_between_parts_of_its_own_po(db, api):
    """Chỉ chuyển CHÉO PO mới bị chặn; đổi Part trong cùng PO vẫn là việc hợp lệ."""
    import io
    import os
    from openpyxl import Workbook

    sfx = _suffix()
    code = f'MOVE-{sfx}'
    with db.cursor() as cur:
        po = _po(cur, f'PO-MV-{sfx}')
        part_a = _part(cur, po, 'PA', 0)
        _part(cur, po, 'PB', 1)
        op_id = _op(cur, po, part_a, code)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Operations'
    sheet.append(['operation_id', 'product', 'po', 'part', 'part_order', 'operation_name',
                  'drawing', 'plan', 'done', 'defect', 'status', 'qr'])
    sheet.append([code, 'SP', f'PO-MV-{sfx}', 'PB', 1, 'Công đoạn', '', 100, 0, 0,
                  'PLANNED', f'WF|OP|{code}'])
    buf = io.BytesIO()
    workbook.save(buf)
    buf.seek(0)

    base = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')
    response = api.post(f'{base}/api/operations/import',
        files={'file': ('ops.xlsx', buf,
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
        data={'mode': 'merge'}, timeout=30)
    assert response.status_code == 200, response.text[:300]
    with db.cursor() as cur:
        cur.execute("""SELECT p.code part_code FROM operations o JOIN parts p ON p.id=o.part_id
            WHERE o.id=%s""", (op_id,))
        assert cur.fetchone()['part_code'] == 'PB'


# ---------------------------------------------------------------- SETUP / REWORK

def test_setup_and_rework_rows_never_borrow_the_production_row_identity(db):
    """OP phụ là hàng riêng, id riêng, sản lượng riêng -- không trộn vào OP sản xuất."""
    from mesflow.db.connection import fetch_one
    from mesflow.domain.qr_identity import resolve_operation_id

    sfx = _suffix()
    with db.cursor() as cur:
        po = _po(cur, f'PO-SU-{sfx}')
        part = _part(cur, po, f'P-{sfx}')
        prod_id = _op(cur, po, part, f'OP-{sfx}', done=10)
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                sort_order,operation_type,parent_operation_id)
            VALUES(%s,%s,%s,'Setup','PLANNED',%s,2147483646,'SETUP',%s) RETURNING id""",
            (po, part, f'OP-{sfx}-SU', f'PENDING-{sfx}', prod_id))
        setup_id = cur.fetchone()['id']
        cur.execute('UPDATE operations SET qr=%s WHERE id=%s', (f'{OPID_PREFIX}{setup_id}', setup_id))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                sort_order,operation_type)
            VALUES(%s,%s,%s,'SỬA HÀNG','PLANNED',%s,2147483647,'REWORK') RETURNING id""",
            (po, part, f'REWORK-{po}-{sfx}', f'WF|OP|REWORK-{po}-{sfx}'))
        rework_id = cur.fetchone()['id']

    assert len({prod_id, setup_id, rework_id}) == 3
    # SETUP treo vào cha bằng id, không bằng mã có hậu tố '-SU'.
    assert fetch_one('SELECT parent_operation_id FROM operations WHERE id=%s',
                     (setup_id,))['parent_operation_id'] == prod_id
    # Tem của mỗi loại giải ra đúng hàng của nó, không lẫn sang OP sản xuất.
    assert resolve_operation_id(f'{OPID_PREFIX}{setup_id}') == setup_id
    assert resolve_operation_id(f'WF|OP|OP-{sfx}') == prod_id
    assert resolve_operation_id(f'WF|OP|REWORK-{po}-{sfx}') == rework_id
    # Sản lượng không bị trộn: OP phụ vẫn 0 sau khi OP sản xuất có 10.
    for support_id in (setup_id, rework_id):
        row = fetch_one('SELECT done_qty,defect_qty,rework_qty FROM operations WHERE id=%s', (support_id,))
        assert (row['done_qty'], row['defect_qty'], row['rework_qty']) == (0, 0, 0)


def test_the_setup_suffix_cannot_silently_collide_with_a_real_operation(db):
    """'-SU' là mã sinh ra, nên nó phải va vào unique chứ không được ghi đè ai."""
    sfx = _suffix()
    with db.cursor() as cur:
        po = _po(cur, f'PO-SUC-{sfx}')
        part = _part(cur, po, f'P-{sfx}')
        parent_id = _op(cur, po, part, f'OP-{sfx}')
        # Một Operation do người dùng tự đặt tên, trùng đúng mã mà SETUP sẽ sinh.
        _op(cur, po, part, f'OP-{sfx}-SU', sort_order=1)
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                    sort_order,operation_type,parent_operation_id)
                VALUES(%s,%s,%s,'Setup','PLANNED',%s,2147483646,'SETUP',%s)""",
                (po, part, f'OP-{sfx}-SU', f'PENDING-{sfx}', parent_id))
