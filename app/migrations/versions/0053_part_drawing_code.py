"""Mã bản vẽ của Part là dữ liệu, không phải thứ đọc xong rồi bỏ.

LÝ DO. Tờ GO ROUTER ghi ``MÃ BẢN VẼ`` ở đầu mỗi sheet, và đó là **danh tính
kỹ thuật** mà cả xưởng dùng để gọi tên chi tiết: thợ đọc nó trên bản vẽ giấy,
kho dán nó lên thùng, QC ghi nó vào phiếu. Importer vẫn đọc ô đó -- nó là thứ
sinh ra mã Part -- nhưng chỉ dùng làm nguyên liệu cho một mã nội bộ rồi thả
rơi. Không bảng nào giữ lại nguyên văn, nên không màn hình nào hiện được nó,
và người dùng không có cách nào đối chiếu Part trên MESFlow với tờ bản vẽ
đang cầm trên tay.

Hai cột, không phải một: ``template_parts.drawing_code`` là mã mà lần nhập
Template đọc được, còn ``parts.drawing_code`` là **bản chụp tại lúc tạo PO**.
Tách ra vì Template còn sửa được sau khi PO đã chạy: nếu PO đọc xuyên sang
Template thì sửa Template sẽ lặng lẽ viết lại tài liệu của một PO đang sản
xuất. Bản chụp KHÔNG hồi tố -- PO đã tạo trước migration này giữ ``NULL``, và
``NULL`` ở đây nói đúng sự thật: lúc đó hệ thống không biết mã bản vẽ.

Cả hai đều nullable. Tờ mức quy trình (sơn, kiểm tra, đóng gói) hợp lệ mà
không có bản vẽ nào -- xem REQ-TPL-007 -- nên ép NOT NULL là bắt xưởng bịa ra
một mã cho một thứ không có bản vẽ.

Lệnh idempotent (``IF NOT EXISTS``): migration được chạy lại trên cùng một cơ
sở dữ liệu trong lúc phát triển, và một lần nâng cấp nửa chừng không được biến
thành một cơ sở dữ liệu không sửa được.
"""
from alembic import op

revision = "0053_part_drawing_code"
down_revision = "0052_router_source_semantics"
branch_labels = None
depends_on = None

#: (bảng, cột, kiểu). Giữ thành dữ liệu để upgrade/downgrade không thể lệch nhau.
COLUMNS = (
    ('template_parts', 'drawing_code', 'TEXT'),
    ('parts', 'drawing_code', 'TEXT'),
)


def upgrade():
    for table, column, type_ in COLUMNS:
        op.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_}')
    op.execute("UPDATE system_meta SET value='72.0.12.0',updated_at=CURRENT_TIMESTAMP "
               "WHERE key='schema_version'")


def downgrade():
    for table, column, _ in COLUMNS:
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS {column}')
