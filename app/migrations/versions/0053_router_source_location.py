"""Vị trí trên tờ giấy của ô "Tổng thời gian gia công dự kiến".

VÌ SAO CẦN. `expected_total_seconds` (0052) đã lưu CON SỐ của khách, và
71.0.0.311 đã đem nó ra đối chiếu với số MESFlow tự tính. Trên file thật hai số
lệch -9,41% (308,64 h so với 279,61 h), và chỗ lệch nằm ở 5/112 công đoạn có
một HỆ SỐ viết thẳng trong công thức Excel:

    'Lắp ráp sau khi sơn'!M14 = $I$4*L14*10/3600 + L11/60

Nhưng một cảnh báo chỉ nói "KM-504539877-B6-OP01 lệch 11 giờ" thì người dùng
vẫn phải mở 44 sheet ra dò tay. Thứ họ cần để tới thẳng chỗ đó là: TỜ NÀO, DÒNG
NÀO ĐẾN DÒNG NÀO, Ô NÀO, và CÔNG THỨC GÌ.

Bốn cột dưới đây lưu đúng chừng ấy, đọc được ngay lúc nhập file mà không phải
mở lại workbook về sau. Chúng là DỮ LIỆU NGUỒN: chép nguyên văn từ tờ giấy,
không bao giờ suy lại từ thứ khác.

An toàn và tương thích ngược tuyệt đối: bốn cột đều NULL được, không ràng buộc,
không backfill, không sửa dòng nào đang có. Template nhập trước bản này giữ
NULL và màn hình chỉ đơn giản không hiện phần vị trí -- mọi thứ khác y nguyên.
"""
from alembic import op

revision = "0053_router_source_location"
down_revision = "0052_router_source_semantics"
branch_labels = None
depends_on = None

#: (bảng, cột, kiểu). Chỉ template_operations: đây là dữ liệu để soi lại TỜ
#: GIẤY GỐC của Template, không phải thứ một PO đang chạy cần biết.
COLUMNS = (
    # Tên sheet và khoảng dòng của block -- một Operation chiếm nhiều dòng, nên
    # chỉ ghi dòng đầu là bắt người dùng tự đoán block kết thúc ở đâu.
    ('template_operations', 'source_sheet', 'TEXT'),
    ('template_operations', 'source_row_start', 'INTEGER'),
    ('template_operations', 'source_row_end', 'INTEGER'),
    # Toạ độ ô tổng (ví dụ 'M14') và công thức nguyên văn trong ô đó. Công thức
    # là thứ DUY NHẤT giải thích được hệ số ẩn: nó không nằm trong ô nào khác.
    ('template_operations', 'expected_total_cell', 'TEXT'),
    ('template_operations', 'expected_total_formula', 'TEXT'),
)


def upgrade():
    for table, column, coltype in COLUMNS:
        op.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}')


def downgrade():
    # Đảo NGƯỢC ĐỦ, không nửa vời: cả năm cột thêm ở trên đều được gỡ, nên một
    # vòng downgrade -> upgrade chạy lại được. (Đây chính là lỗi của 0029, thứ
    # audit 2026-09-14 ghi lại là DB-14.)
    for table, column, _coltype in reversed(COLUMNS):
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS {column}')
