"""Sự kiện kiosk offline được phép thử lại, thay vì hỏng một lần là mất.

VẤN ĐỀ. kiosk_client_events.status hiện chỉ có ba giá trị thật:
'accepted', 'duplicate', 'rejected'. Mọi lỗi nghiệp vụ -- kể cả loại chỉ TẠM
thời đúng như "OP nguồn chưa có sản lượng để cấp" hay "OP chưa được phép bắt
đầu" -- đều thành 'rejected', là trạng thái cuối. Thiết bị nhận 'rejected' thì
bỏ sự kiện đi. Một ca làm việc có thật, ghi ở kiosk lúc mất mạng, biến mất chỉ
vì lúc đồng bộ thì công đoạn phía trước chưa kịp nhập số.

Chiều ngược lại cũng hở: lỗi hạ tầng trả 'transient' và CỐ Ý không ghi dòng
nào, để thiết bị giữ và thử lại. Đúng cho thiết bị, nhưng phía máy chủ thì
không còn dấu vết gì -- không ai biết có bao nhiêu sự kiện đang kẹt.

THAY ĐỔI. Thêm attempt_count để đếm số lần một client_event_id quay lại, và mở
rộng tập status thành vòng đời đầy đủ:

    PROCESSING -> accepted | duplicate | retryable | rejected

'retryable' là trạng thái MỚI, không phải trạng thái cuối: máy chủ giữ dòng
kèm lý do (nên nhìn thấy được), còn thiết bị vẫn nhận 'transient' để tiếp tục
giữ và gửi lại. Không đổi firmware ESP -- hợp đồng phía thiết bị y nguyên.

Khi attempt_count vượt ngưỡng, dòng chuyển sang 'rejected' với
reason_code='RETRY_EXHAUSTED': thử mãi không được thì phải dừng, nhưng dừng
một cách nhìn thấy được chứ không im lặng.

Cột thêm mới, có DEFAULT, không ràng buộc mới -- dữ liệu cũ đọc ghi bình
thường, không phá tương thích.
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_offline_event_retry_lifecycle"
down_revision = "0048_setup_note_replaces_checklist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kiosk_client_events",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "kiosk_client_events",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Câu hỏi vận hành duy nhất của bảng này là "còn sự kiện nào đang kẹt
    # không, của kiosk nào" -- index đúng theo hình dạng đó.
    op.create_index(
        "idx_kiosk_client_events_retryable",
        "kiosk_client_events",
        ["kiosk_id", "status"],
        postgresql_where=sa.text("status = 'retryable'"),
    )
    op.execute("UPDATE system_meta SET value='72.0.9.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade() -> None:
    op.execute("UPDATE system_meta SET value='72.0.8.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.drop_index("idx_kiosk_client_events_retryable", table_name="kiosk_client_events")
    op.drop_column("kiosk_client_events", "last_attempt_at")
    op.drop_column("kiosk_client_events", "attempt_count")
