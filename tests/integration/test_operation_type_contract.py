"""Cột sinh is_rework_op và policy phải nói cùng một điều.

BỐI CẢNH. Trước policy, hệ thống phân loại OP sửa hàng bằng cột sinh
``is_rework_op`` (``operation_type = 'REWORK'``, STORED). Sau khi quét sang
policy, hai cách vẫn cùng tồn tại: policy dùng ở chỗ ra quyết định, còn cột
sinh vẫn được CHIẾU ra trong payload của kiosk (execution.OPERATION_FIELDS) --
firmware đang đọc nó, và đổi hợp đồng phía thiết bị không nằm trong phạm vi.

Hai cách phân loại song song là đúng thứ đã sinh ra mọi lỗi trong module này.
Chúng an toàn CHỈ KHI chứng minh được là tương đương. Bài test chứng minh ở hai
mức:

  * định nghĩa -- biểu thức sinh của cột phải khớp policy;
  * dữ liệu -- không dòng nào trong bảng cho hai câu trả lời khác nhau.

Nếu ai đó sửa biểu thức sinh (ví dụ thêm SETUP vào), bài test đỏ ngay thay vì
để hai nửa hệ thống lặng lẽ bất đồng.
"""
from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.postgres


def test_generated_column_expression_matches_the_policy():
    from mesflow.domain.policy import REWORK_TYPE
    from mesflow.db.connection import fetch_one

    row = fetch_one("""SELECT generation_expression FROM information_schema.columns
        WHERE table_name='operations' AND column_name='is_rework_op'""")
    assert row, 'cột sinh is_rework_op không còn -- cập nhật hoặc gỡ bài test này'
    expression = row['generation_expression']
    # Postgres viết lại biểu thức với ép kiểu; chỉ cần nó so operation_type với
    # đúng REWORK và không nhắc tới loại nào khác.
    assert 'operation_type' in expression, expression
    assert f"'{REWORK_TYPE}'" in expression, expression
    for other in ('SETUP', 'PRODUCTION'):
        assert f"'{other}'" not in expression, (
            f'biểu thức sinh nhắc tới {other} -- nó không còn tương đương policy: {expression}')


def test_no_row_disagrees_between_the_two_classifications(db):
    """Kiểm trên MỌI dòng đang có, không phải trên vài dòng dựng sẵn."""
    row = db.execute("""SELECT
        COUNT(*) FILTER (WHERE is_rework_op IS DISTINCT FROM
                         (COALESCE(operation_type,'PRODUCTION')='REWORK')) AS lech,
        COUNT(*) AS tong FROM operations""").fetchone()
    assert row['lech'] == 0, (
        f"{row['lech']}/{row['tong']} dòng cho hai câu trả lời khác nhau giữa "
        'is_rework_op và policy')


def test_a_row_of_each_type_classifies_the_same_way(db):
    """Dựng đủ ba loại rồi hỏi cả hai cách -- bảng rỗng thì bài trên vô nghĩa."""
    import uuid
    from mesflow.domain.policy import is_rework

    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',10,'IN_PROGRESS') RETURNING id""", (f'PO-CT-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Chính','PLANNED',%s,0) RETURNING id""",
            (po_id, part_id, f'CT-{suffix}-P', f'WF|OP|CT-{suffix}-P'))
        main_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,
                operation_type,parent_operation_id)
            VALUES(%s,%s,%s,'Setup','PLANNED',%s,1,'SETUP',%s)""",
            (po_id, part_id, f'CT-{suffix}-S', f'WF|OP|CT-{suffix}-S', main_id))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,
                operation_type) VALUES(%s,%s,%s,'SỬA HÀNG','PLANNED',%s,2,'REWORK')""",
            (po_id, part_id, f'CT-{suffix}-R', f'WF|OP|CT-{suffix}-R'))
    try:
        rows = db.execute("""SELECT operation_type,is_rework_op FROM operations
            WHERE production_order_id=%s ORDER BY sort_order""", (po_id,)).fetchall()
        assert len(rows) == 3
        for row in rows:
            assert bool(row['is_rework_op']) == is_rework(row['operation_type']), row
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_the_rework_bench_lookup_finds_the_same_row_either_way(db):
    """Truy vấn tra bàn SỬA HÀNG: dạng cũ và dạng policy phải ra cùng một dòng.

    Đây là câu truy vấn thật đã đổi ở 71.0.0.275. Đã kiểm bằng EXPLAIN rằng hai
    dạng cho kế hoạch tương đương (cost 8.16 vs 8.17, cả hai Index Scan theo
    (production_order_id, part_id) rồi Filter), nên đổi không mất index.
    """
    import uuid
    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',10,'IN_PROGRESS') RETURNING id""", (f'PO-CT2-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Chính','PLANNED',%s,0)""",
            (po_id, part_id, f'CT2-{suffix}-P', f'WF|OP|CT2-{suffix}-P'))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,
                operation_type) VALUES(%s,%s,%s,'SỬA HÀNG','PLANNED',%s,1,'REWORK') RETURNING id""",
            (po_id, part_id, f'CT2-{suffix}-R', f'WF|OP|CT2-{suffix}-R'))
        expected = cur.fetchone()['id']
    try:
        old = db.execute("""SELECT o.id FROM operations o
            WHERE o.production_order_id=%s AND o.part_id=%s AND o.is_rework_op=TRUE
            ORDER BY o.id LIMIT 1""", (po_id, part_id)).fetchone()
        new = db.execute("""SELECT o.id FROM operations o
            WHERE o.production_order_id=%s AND o.part_id=%s
              AND COALESCE(o.operation_type,'PRODUCTION')='REWORK'
            ORDER BY o.id LIMIT 1""", (po_id, part_id)).fetchone()
        assert old and new and old['id'] == new['id'] == expected
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
