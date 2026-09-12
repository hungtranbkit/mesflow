"""Migration 0053: mã bản vẽ của Part phải là CỘT, và không hồi tố.

Hai điều cần chứng minh, và điều thứ hai mới là điều dễ làm sai:

  * cột tồn tại ở CẢ hai bảng -- ``template_parts`` (mã đọc được lúc nhập) và
    ``parts`` (bản chụp lúc tạo PO). Chỉ có một cột là sai: hoặc PO đọc xuyên
    sang Template (sửa Template viết lại tài liệu của PO đang chạy), hoặc
    Template không giữ được mã để mà chụp;
  * dữ liệu có TRƯỚC migration giữ ``NULL``, không phải chuỗi rỗng. Lúc đó hệ
    thống thật sự không biết mã bản vẽ, và ``NULL`` nói đúng như vậy. Chuỗi
    rỗng sẽ là một lời khai báo "Part này không có bản vẽ" mà không ai viết.

Và cột phải NULLABLE: tờ mức quy trình (sơn, kiểm tra, đóng gói) hợp lệ mà
không có bản vẽ nào -- xem REQ-TPL-007.
"""
import os
import subprocess

import pytest

pytestmark = pytest.mark.integration

NEW_COLUMNS = (
    ('template_parts', 'drawing_code'),
    ('parts', 'drawing_code'),
)


def _column(db, table, column):
    return db.execute("""SELECT data_type,is_nullable,column_default
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s""", (table, column)).fetchone()


def test_cot_ton_tai_o_ca_hai_bang(db):
    for table, column in NEW_COLUMNS:
        assert _column(db, table, column), f'{table}.{column} chưa được tạo'


def test_cot_nullable_va_khong_co_default(db):
    """Tờ quy trình không có bản vẽ là hợp lệ; ép NOT NULL là bắt bịa ra mã."""
    for table, column in NEW_COLUMNS:
        info = _column(db, table, column)
        assert info['is_nullable'] == 'YES', f'{table}.{column} không được NOT NULL'
        assert info['column_default'] is None, f'{table}.{column} không được có default'


def test_du_lieu_cu_giu_NULL_chu_khong_phai_chuoi_rong(db):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO templates(code,name,product,version,active)
            VALUES('TPL-MIG0053','Template cũ','SP','1.0',true) RETURNING id""")
        template_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
            VALUES(%s,'P-OLD','Part cũ',0) RETURNING id""", (template_id,))
        template_part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES('PO-MIG0053','SP',10,'PLANNED') RETURNING id""")
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'P-OLD','Part cũ',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
    try:
        assert db.execute('SELECT drawing_code FROM template_parts WHERE id=%s',
                          (template_part_id,)).fetchone()['drawing_code'] is None
        assert db.execute('SELECT drawing_code FROM parts WHERE id=%s',
                          (part_id,)).fetchone()['drawing_code'] is None
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
            cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))


def test_schema_version_da_tang(db):
    version = db.execute("SELECT value FROM system_meta WHERE key='schema_version'").fetchone()
    assert version['value'] == '72.0.12.0'


@pytest.mark.skipif(not os.environ.get('MESFLOW_MIGRATION_RERUN'),
                    reason='chạy lại alembic cần CLI trong image ứng dụng; '
                           'bật bằng MESFLOW_MIGRATION_RERUN=1')
def test_chay_lai_upgrade_khong_no(db):
    result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True,
                            cwd='/app', env={**os.environ})
    assert result.returncode == 0, result.stderr[-2000:]
    for table, column in NEW_COLUMNS:
        assert _column(db, table, column)
