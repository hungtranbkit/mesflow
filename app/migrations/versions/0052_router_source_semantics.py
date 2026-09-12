"""Giữ lại ý nghĩa của tờ Router, thay vì chỉ giữ tên Part/OP.

LÝ DO. Tờ GO ROUTER là tài liệu nghiệp vụ của khách, không phải một danh sách
tên. Trước migration này, import đọc đúng bốn thứ — mã Part, tên Part, tên OP,
thời gian setup/cycle — và mọi thứ còn lại rơi mất *im lặng*. Audit file thật
(`docs/ROUTER_IMPORT_FIELD_AUDIT.md`, PO 6126, 44 sheet, 112 block) cho thấy cụ
thể cái gì đang rơi:

  * ``SỐ LƯỢNG`` riêng của từng sheet — 32 sheet ghi 110, 11 sheet ghi 220, 1
    sheet ghi 440. Đây là bội số BOM, KHÔNG phải bản sao của QTY cấp PO. Mất nó
    là mất định mức của 12 Part.
  * ``Tổng thời gian gia công dự kiến`` — 5 công đoạn cố ý không khớp
    ``qty × cycle`` vì chúng mã hoá số LẦN THAO TÁC riêng (ĐÓNG ECU VÀO NAN GỖ:
    40s/sp nhưng tổng 12,2222h ⇒ 1100 lần, gấp 10 lần QTY 110). Suy lại từ số
    lượng là ghi đè định mức thật bằng một phép tính sai.
  * Số OP gốc — 10 chỗ trong file dùng lại một số cho hai công đoạn khác nhau
    (OPERATION # 02 vừa là CHAMFER LỖ vừa là LÀM NGUỘI). Mã nội bộ phải duy
    nhất, nhưng con số TRÊN GIẤY là thứ thợ đọc, nên phải giữ nguyên văn.
  * ``Thời gian Setup`` có ba trạng thái, không phải hai: ``> 0``, ``0``, và
    dấu ``-`` (6 block). Cả ``0`` lẫn ``-`` đều không sinh OP SETUP, nhưng ``-``
    nghĩa là "không áp dụng" còn ``0`` là "có khai báo và bằng không". Ép cả
    hai về 0 là bịa ra một lời khai báo mà xưởng không viết.

Không cột nào ở đây là NOT NULL. Dữ liệu có trước migration này đơn giản là
không biết những điều đó, và ``NULL`` nói đúng như vậy — khác hẳn ``0``, vốn là
một lời khai báo. Đó cũng là lý do việc nâng cấp chạy được trên dữ liệu cũ mà
không cần backfill đoán mò.

Mọi lệnh đều idempotent (``IF NOT EXISTS``): migration này được chạy lại trên
cùng một cơ sở dữ liệu trong lúc phát triển, và một lần nâng cấp nửa chừng
không được biến thành một cơ sở dữ liệu không sửa được.
"""
from alembic import op

revision = "0052_router_source_semantics"
down_revision = "0051_repair_pending_semantics"
branch_labels = None
depends_on = None


#: (bảng, cột, kiểu). Giữ thành dữ liệu để upgrade/downgrade không thể lệch nhau.
COLUMNS = (
    # --- số lượng ---------------------------------------------------------
    # Số lượng Part phải làm, theo ô SỐ LƯỢNG của chính sheet đó. Độc lập với
    # production_orders.planned_quantity (QTY cấp PO).
    ('template_parts', 'planned_quantity', 'INTEGER'),
    ('parts', 'planned_quantity', 'INTEGER'),

    # --- danh tính nguồn --------------------------------------------------
    # Số OP và tiêu đề ĐÚNG NHƯ TRÊN GIẤY. code vẫn là mã nội bộ duy nhất;
    # operation.id vẫn là danh tính canonical.
    ('template_operations', 'source_op_no', 'INTEGER'),
    ('template_operations', 'source_title', 'TEXT'),
    ('operations', 'source_op_no', 'INTEGER'),
    ('operations', 'source_title', 'TEXT'),

    # --- thời gian -------------------------------------------------------
    # Tổng thời gian dự kiến do xưởng ghi, quy về giây. NGUỒN, không suy lại.
    ('template_operations', 'expected_total_seconds', 'DOUBLE PRECISION'),
    ('operations', 'expected_total_seconds', 'DOUBLE PRECISION'),
    # Nguyên văn ô Thời gian Setup: '20', '0', '-' ... Phân biệt ba trạng thái.
    ('template_operations', 'setup_source_raw', 'TEXT'),
    ('operations', 'setup_source_raw', 'TEXT'),

    # --- metadata biểu mẫu ------------------------------------------------
    ('templates', 'order_type', 'TEXT'),
    ('templates', 'source_document_meta', 'TEXT'),
    ('production_orders', 'order_type', 'TEXT'),
)

#: Bảng nối blob <-> Template. Bytes đã được lưu content-addressed từ 0046;
#: cái thiếu là "Template NÀY dựng từ file NÀO", và nó phải ghi TRONG cùng
#: transaction tạo Template -- nếu không, một lần rollback để lại con trỏ tới
#: một Template chưa từng tồn tại.
LINK_TABLE = """
CREATE TABLE IF NOT EXISTS template_source_workbooks (
    id              BIGSERIAL PRIMARY KEY,
    template_id     BIGINT NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    blob_id         BIGINT NOT NULL REFERENCES template_import_blobs(id) ON DELETE RESTRICT,
    sha256          VARCHAR(64) NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    linked_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_template_source_workbook UNIQUE (template_id, sha256)
)
"""


def upgrade():
    for table, column, type_ in COLUMNS:
        op.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_}')
    op.execute(LINK_TABLE)
    # Tra "file này đã nhập chưa" là đường nóng của kiểm tra idempotent, và nó
    # tra theo sha256 chứ không theo template_id.
    op.execute('CREATE INDEX IF NOT EXISTS idx_template_source_workbooks_sha256 '
               'ON template_source_workbooks (sha256)')
    op.execute("UPDATE system_meta SET value='72.0.11.0',updated_at=CURRENT_TIMESTAMP "
               "WHERE key='schema_version'")


def downgrade():
    op.execute('DROP INDEX IF EXISTS idx_template_source_workbooks_sha256')
    op.execute('DROP TABLE IF EXISTS template_source_workbooks')
    for table, column, _ in COLUMNS:
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS {column}')
