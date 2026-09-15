"""Một nhân viên giữ nhiều Operation cùng lúc -- nhưng không bao giờ hai lần
cùng MỘT Operation.

VÌ SAO CẦN. Từ migration 0003, `uq_open_session_per_employee` (UNIQUE trên
work_sessions(employee_id) WHERE status='OPEN') cho phép đúng MỘT session OPEN
mỗi người. Trên sàn thật một người thường trông 2-3 máy cùng lúc; ràng buộc đó
buộc họ phải kết thúc việc đang chạy trước khi bắt đầu việc kế, tức ghi sai cả
hai mốc thời gian.

RÀNG BUỘC MỚI YẾU HƠN ĐÚNG MỘT BẬC, không phải bỏ trắng: thêm operation_id vào
khoá. Nhiều OPEN cho một người thì được; hai OPEN cho cùng (người, Operation)
thì không.

Đó KHÔNG phải một lựa chọn tuỳ tiện -- nó là điều kiện để cả UX quét mã chạy
được. Máy quét chỉ đọc được tem Operation; nếu một người có thể mở hai session
trên cùng một Operation thì tem đó không còn định danh duy nhất session nào, và
màn hình buộc phải bắt người đứng máy chọn tay. Với ràng buộc này, "quét thẻ
rồi quét tem" luôn giải ra đúng một session.

AN TOÀN KHI ĐI LÊN. Ràng buộc cũ HÀM Ý ràng buộc mới: đã chỉ có một OPEN mỗi
người thì không thể có hai OPEN cùng (người, Operation). Nên index mới không
bao giờ có thể build lỗi trên dữ liệu đang có -- không cần dọn dữ liệu, không
cần cửa sổ bảo trì, không đụng một dòng work_sessions nào.

ĐI XUỐNG THÌ KHÔNG ĐỐI XỨNG. Dựng lại index cũ sẽ THẤT BẠI nếu lúc đó đã có
người đang giữ nhiều session OPEN. Bản này CỐ Ý không tự đóng bớt session để
lách: một session OPEN là công việc thật đang diễn ra ngoài xưởng, đóng nó bằng
giờ máy chủ là bịa ra dữ liệu sản xuất. Downgrade dừng lại và nói rõ phải làm
gì, thay vì làm hỏng lặng lẽ.
"""
from alembic import op

revision = "0054_multi_open_session_per_employee"
down_revision = "0053_router_source_location"
branch_labels = None
depends_on = None

OLD_INDEX = "uq_open_session_per_employee"
NEW_INDEX = "uq_open_session_per_employee_operation"


def upgrade():
    # Không CONCURRENTLY: alembic chạy trong một transaction, và
    # CREATE INDEX CONCURRENTLY không dùng được ở đó. Bảng work_sessions khoá
    # rất ngắn cho một partial index trên hai cột; lock_timeout dưới đây là để
    # một deploy không treo cả xưởng nếu đúng lúc đó có transaction dài.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP INDEX IF EXISTS {OLD_INDEX}")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX} "
        "ON work_sessions(employee_id, operation_id) WHERE status='OPEN'"
    )


def downgrade():
    # PREFLIGHT, không mutate. Nếu dữ liệu hiện tại không biểu diễn được dưới
    # ràng buộc cũ thì dừng và nói rõ -- CREATE INDEX bên dưới dù sao cũng sẽ
    # tự nổ, nhưng nó nổ bằng một lỗi Postgres không nói được ai đang mở cái
    # gì. Người vận hành cần chính danh sách đó để đi đóng từng session cho
    # đúng, bằng giờ thật.
    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        "SELECT employee_id, COUNT(*) AS open_count, "
        "       array_agg(id ORDER BY id) AS session_ids "
        "FROM work_sessions WHERE status='OPEN' "
        "GROUP BY employee_id HAVING COUNT(*) > 1 ORDER BY employee_id"
    ).fetchall()
    if rows:
        detail = "; ".join(f"employee_id={r[0]} có {r[1]} session OPEN {list(r[2])}" for r in rows)
        raise RuntimeError(
            f"MULTI_OPEN_SESSIONS_PRESENT: {len(rows)} nhân viên đang giữ nhiều session OPEN "
            f"({detail}). Ràng buộc cũ {OLD_INDEX} không biểu diễn được trạng thái này. "
            "Hãy kết thúc các session đó qua kiosk hoặc màn Quản lý Session (bằng giờ THẬT) "
            "rồi chạy lại downgrade. Bản migration này cố ý KHÔNG tự đóng session: "
            "đóng bằng giờ máy chủ là bịa ra dữ liệu sản xuất."
        )
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"DROP INDEX IF EXISTS {NEW_INDEX}")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {OLD_INDEX} "
        "ON work_sessions(employee_id) WHERE status='OPEN'"
    )
