"""Mỗi bộ dò danh tính phải BẮT ĐƯỢC ca hỏng của chính nó.

Một bộ dò không bao giờ trả về dòng nào trông y hệt một hệ thống sạch. Đó
không phải giả thuyết: `_ambiguous_operation_code()` cũ đi tìm hai Operation
cùng mã, trong khi `operations_code_key` cấm đúng điều đó -- câu truy vấn ấy
không thể trả về dòng nào, và sự im lặng của nó được đọc thành "không có vấn
đề" suốt thời gian nó tồn tại.

Nên mỗi bài ở đây làm hai việc, theo thứ tự: dựng ca hỏng và đòi bộ dò TÌM
THẤY nó, rồi dọn đi và đòi bộ dò IM LẶNG. Bộ dò nào chỉ qua được vế sau là bộ
dò chết.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.postgres


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


def _run(category: str):
    from mesflow.services.integrity_audit_service import audit_integrity
    report = audit_integrity()
    assert category in report, f'thiếu hạng mục {category}: {sorted(report)}'
    return report[category]


@pytest.fixture
def po_part(db):
    sfx = _suffix()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-DET-{sfx}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,%s,'Part',0) RETURNING id",
                    (po_id, f'PART-{sfx}'))
        part_id = cur.fetchone()['id']
    yield {'po_id': po_id, 'part_id': part_id, 'suffix': sfx}
    with db.cursor() as cur:
        cur.execute("DELETE FROM operations WHERE production_order_id=%s", (po_id,))
        cur.execute("DELETE FROM parts WHERE production_order_id=%s", (po_id,))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (po_id,))


def test_ambiguous_operation_qr_is_found_then_silent(db, po_part):
    """Ca CÓ THẬT: tem cũ của hàng A trùng với mã của hàng B."""
    sfx = po_part['suffix']
    code = f'DETAMB-{sfx}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'A','PLANNED',%s,0) RETURNING id""",
            (po_part['po_id'], po_part['part_id'], code, f'WF|OP|{code}'))
        a_id = cur.fetchone()['id']
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{code}-OLD', a_id))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'B','PLANNED',%s,1) RETURNING id""",
            (po_part['po_id'], po_part['part_id'], code, f'WF|OPID|X-{sfx}'))
        b_id = cur.fetchone()['id']

    rows = _run('AMBIGUOUS_OPERATION_QR')
    mine = [r for r in rows if r['qr_owner_id'] == a_id]
    assert mine, f'không bắt được tem mơ hồ giữa {a_id} và {b_id}: {rows}'
    assert mine[0]['code_owner_id'] == b_id, mine

    with db.cursor() as cur:
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{code}-B', b_id))
    assert not [r for r in _run('AMBIGUOUS_OPERATION_QR') if r['qr_owner_id'] == a_id]


def test_ambiguous_employee_badge_is_found_then_silent(db):
    sfx = _suffix()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'A',%s,true) RETURNING id""", (f'D1-{sfx}', f'WF|EMP|D2-{sfx}'))
        a_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'B',%s,true) RETURNING id""", (f'D2-{sfx}', f'BADGE-{sfx}'))
        b_id = cur.fetchone()['id']
    try:
        rows = _run('AMBIGUOUS_EMPLOYEE_BADGE')
        assert [r for r in rows if r['qr_owner_id'] == a_id and r['no_owner_id'] == b_id], rows
        with db.cursor() as cur:
            cur.execute("UPDATE employees SET active=false WHERE id=%s", (b_id,))
        assert not [r for r in _run('AMBIGUOUS_EMPLOYEE_BADGE') if r['qr_owner_id'] == a_id]
    finally:
        with db.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id = ANY(%s)", ([a_id, b_id],))


def test_duplicate_display_key_in_part_is_found(db, po_part):
    """Mã trong bảng khác nhau, nhưng trên màn hình là một."""
    sfx = po_part['suffix']
    part_code = f'PART-{sfx}'
    with db.cursor() as cur:
        # 'X' và '<part>-X' trong cùng một Part gấp về cùng một display key.
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'A','PLANNED',%s,0)""",
            (po_part['po_id'], po_part['part_id'], f'DUPX-{sfx}', f'WF|OP|DUPX-{sfx}'))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'B','PLANNED',%s,1)""",
            (po_part['po_id'], po_part['part_id'], f'{part_code}-DUPX-{sfx}',
             f'WF|OP|{part_code}-DUPX-{sfx}'))
    rows = _run('DUPLICATE_DISPLAY_KEY_IN_PART')
    assert [r for r in rows if r['part_id'] == po_part['part_id']], rows


def test_material_source_unresolved_and_cross_po_are_found(db, po_part):
    sfx = po_part['suffix']
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                sort_order,input_flow_enabled) VALUES(%s,%s,%s,'A','PLANNED',%s,0,true) RETURNING id""",
            (po_part['po_id'], po_part['part_id'], f'NOSRC-{sfx}', f'WF|OP|NOSRC-{sfx}'))
        orphan_id = cur.fetchone()['id']
    assert [r for r in _run('MATERIAL_SOURCE_UNRESOLVED') if r['operation_id'] == orphan_id]

    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',10,'IN_PROGRESS') RETURNING id""", (f'PO-OTHER-{sfx}',))
        other_po = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,%s,'P',0) RETURNING id",
                    (other_po, f'OP2-{sfx}'))
        other_part = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Nguồn','PLANNED',%s,0) RETURNING id""",
            (other_po, other_part, f'FARSRC-{sfx}', f'WF|OP|FARSRC-{sfx}'))
        far_src = cur.fetchone()['id']
        cur.execute("UPDATE operations SET input_source_operation_id=%s WHERE id=%s", (far_src, orphan_id))
    try:
        assert [r for r in _run('MATERIAL_SOURCE_OUTSIDE_ITS_PO') if r['operation_id'] == orphan_id]
    finally:
        with db.cursor() as cur:
            cur.execute("UPDATE operations SET input_source_operation_id=NULL WHERE id=%s", (orphan_id,))
            cur.execute("DELETE FROM operations WHERE production_order_id=%s", (other_po,))
            cur.execute("DELETE FROM parts WHERE production_order_id=%s", (other_po,))
            cur.execute("DELETE FROM production_orders WHERE id=%s", (other_po,))


def test_setup_parent_in_another_part_is_found(db, po_part):
    sfx = po_part['suffix']
    with db.cursor() as cur:
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,%s,'P2',1) RETURNING id",
                    (po_part['po_id'], f'PART2-{sfx}'))
        other_part = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cha','PLANNED',%s,0) RETURNING id""",
            (po_part['po_id'], po_part['part_id'], f'PARENT-{sfx}', f'WF|OP|PARENT-{sfx}'))
        parent_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                sort_order,operation_type,parent_operation_id)
            VALUES(%s,%s,%s,'Setup','PLANNED',%s,2147483646,'SETUP',%s) RETURNING id""",
            (po_part['po_id'], other_part, f'PARENT-{sfx}-SU', f'WF|OPID|S-{sfx}', parent_id))
        setup_id = cur.fetchone()['id']
    assert [r for r in _run('SETUP_PARENT_WRONG_SCOPE') if r['setup_id'] == setup_id]


def test_duplicate_rework_bench_is_found(db, po_part):
    sfx = po_part['suffix']
    with db.cursor() as cur:
        for n in (1, 2):
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                    sort_order,operation_type)
                VALUES(%s,%s,%s,'SỬA HÀNG','PLANNED',%s,2147483647,'REWORK')""",
                (po_part['po_id'], po_part['part_id'], f'RW{n}-{sfx}', f'WF|OP|RW{n}-{sfx}'))
    rows = _run('REWORK_BENCH_DUPLICATED')
    assert [r for r in rows if r['part_id'] == po_part['part_id']], rows


def test_every_identity_detector_is_registered_and_returns_a_list():
    """Không hạng mục nào được biến mất im lặng khỏi báo cáo."""
    from mesflow.services.integrity_audit_service import audit_integrity
    report = audit_integrity()
    for category in ('AMBIGUOUS_OPERATION_QR', 'AMBIGUOUS_EMPLOYEE_BADGE',
                     'DUPLICATE_DISPLAY_KEY_IN_PART', 'MATERIAL_SOURCE_UNRESOLVED',
                     'MATERIAL_SOURCE_OUTSIDE_ITS_PO', 'SETUP_PARENT_WRONG_SCOPE',
                     'REWORK_BENCH_DUPLICATED', 'REWORK_LEDGER_OPERATION_MISMATCH',
                     'OFFLINE_EVENTS_AMBIGUOUS'):
        assert category in report, f'thiếu {category}'
        assert isinstance(report[category], list), category
