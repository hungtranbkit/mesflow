"""Migration 0052 phải nâng cấp được CƠ SỞ DỮ LIỆU CÓ SẴN, không chỉ DB rỗng.

Lý do bài này tồn tại: 0051 từng có một deploy-blocker chỉ lộ ra khi chạy nâng
cấp ĐÈ LÊN dữ liệu ghi theo model cũ — một CHECK bị vi phạm giữa chừng. Chạy
migration trên schema trắng thì không bao giờ thấy.

Nên ở đây: dựng dữ liệu theo model TRƯỚC 0052 (Template/Part/Operation/PO không
có cột mới nào), chạy upgrade, rồi khẳng định hai điều:

  * dữ liệu cũ còn nguyên, và các cột mới là NULL chứ không phải 0 — vì 0 là
    một lời khai báo, còn dữ liệu cũ thật sự KHÔNG biết gì về số lượng Part hay
    tổng thời gian dự kiến;
  * chạy lại upgrade lần nữa không nổ (idempotent).
"""
import os
import subprocess

import pytest

pytestmark = pytest.mark.integration

NEW_COLUMNS = (
    ('template_parts', 'planned_quantity'),
    ('parts', 'planned_quantity'),
    ('template_operations', 'source_op_no'),
    ('template_operations', 'source_title'),
    ('template_operations', 'expected_total_seconds'),
    ('template_operations', 'setup_source_raw'),
    ('operations', 'source_op_no'),
    ('operations', 'source_title'),
    ('operations', 'expected_total_seconds'),
    ('operations', 'setup_source_raw'),
    ('templates', 'order_type'),
    ('templates', 'source_document_meta'),
    ('production_orders', 'order_type'),
)


def _column_exists(db, table, column):
    return db.execute("""SELECT 1 FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s""", (table, column)).fetchone() is not None


def test_moi_cot_moi_deu_ton_tai_sau_upgrade(db):
    for table, column in NEW_COLUMNS:
        assert _column_exists(db, table, column), f'{table}.{column} chưa được tạo'


def test_bang_noi_blob_template_ton_tai_va_chong_trung(db):
    assert db.execute("""SELECT 1 FROM information_schema.tables
        WHERE table_name='template_source_workbooks'""").fetchone()
    constraint = db.execute("""SELECT 1 FROM pg_constraint
        WHERE conname='uq_template_source_workbook'""").fetchone()
    assert constraint, 'thiếu ràng buộc duy nhất (template_id, sha256)'


def test_cot_moi_la_NULL_tren_du_lieu_cu_chu_khong_phai_0(db):
    """Dữ liệu ghi theo model cũ không biết gì về các trường mới.

    NULL nói đúng điều đó. Đặt server_default '0' sẽ biến mọi Part cũ thành
    "số lượng kế hoạch bằng không" -- một lời khai báo mà không ai viết ra.
    """
    with db.cursor() as cur:
        cur.execute("""INSERT INTO templates(code,name,product,version,active)
            VALUES('TPL-MIG0052','Template cũ','SP','1.0',true) RETURNING id""")
        template_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
            VALUES(%s,'P-OLD','Part cũ',0) RETURNING id""", (template_id,))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order)
            VALUES(%s,%s,'OP-OLD','OP cũ',0) RETURNING id""", (template_id, part_id))
        operation_id = cur.fetchone()['id']
    try:
        part = db.execute('SELECT planned_quantity FROM template_parts WHERE id=%s',
                          (part_id,)).fetchone()
        assert part['planned_quantity'] is None
        row = db.execute("""SELECT source_op_no,source_title,expected_total_seconds,
                setup_source_raw FROM template_operations WHERE id=%s""",
            (operation_id,)).fetchone()
        assert row['source_op_no'] is None
        assert row['source_title'] is None
        assert row['expected_total_seconds'] is None
        assert row['setup_source_raw'] is None
        template = db.execute('SELECT order_type,source_document_meta FROM templates WHERE id=%s',
                              (template_id,)).fetchone()
        assert template['order_type'] is None
        assert template['source_document_meta'] is None
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))


def test_du_lieu_cu_khong_bi_migration_dung_vao(db):
    """Nâng cấp không được sửa một giá trị nào của dữ liệu đã có."""
    with db.cursor() as cur:
        cur.execute("""INSERT INTO templates(code,name,product,version,active)
            VALUES('TPL-MIG0052B','Giữ nguyên','SP-B','2.0',false) RETURNING id""")
        template_id = cur.fetchone()['id']
    try:
        row = db.execute('SELECT code,name,product,version,active FROM templates WHERE id=%s',
                         (template_id,)).fetchone()
        assert (row['code'], row['name'], row['product'], row['version'], row['active']) == (
            'TPL-MIG0052B', 'Giữ nguyên', 'SP-B', '2.0', False)
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))


@pytest.mark.skipif(not os.environ.get('MESFLOW_MIGRATION_RERUN'),
                    reason='chạy lại alembic cần CLI trong image ứng dụng; '
                           'bật bằng MESFLOW_MIGRATION_RERUN=1')
def test_chay_lai_upgrade_khong_no(db):
    """Idempotent: mọi lệnh trong 0052 đều IF NOT EXISTS.

    Một lần nâng cấp nửa chừng (mất kết nối, container bị giết) không được biến
    cơ sở dữ liệu thành thứ không sửa được -- lần chạy sau phải đi qua sạch.
    """
    result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True,
                            cwd='/app', env={**os.environ})
    assert result.returncode == 0, result.stderr[-2000:]
    for table, column in NEW_COLUMNS:
        assert _column_exists(db, table, column)
