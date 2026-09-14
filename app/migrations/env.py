import os

from alembic import context
from sqlalchemy import create_engine, pool

from mesflow.core.config import settings

config = context.config
target_metadata = None


def _sqlalchemy_url(database_url: str) -> str:
    """Use SQLAlchemy's psycopg v3 dialect without changing the app DSN."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    raise RuntimeError("Alembic requires a PostgreSQL DATABASE_URL")


SA_DATABASE_URL = _sqlalchemy_url(settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=SA_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


#: Chờ nhiều nhất chừng này để LẤY KHOÁ, rồi bỏ cuộc.
#:
#: VÌ SAO CẦN. Toàn bộ chuỗi 0001->00NN chạy trong MỘT transaction, và trong đó
#: có những lệnh cần ACCESS EXCLUSIVE trên work_sessions (0044) cùng một lần
#: viết lại cả bảng operations (0047 thêm cột generated STORED). Nếu lúc ấy có
#: dù chỉ MỘT transaction đang đọc còn mở -- một autovacuum, một báo cáo chậm,
#: một tab psql ai đó quên -- thì `ALTER TABLE` xếp hàng vô thời hạn, và mọi
#: lệnh START/FINISH của kiosk lại xếp hàng sau NÓ. Cả xưởng đứng, không có
#: giới hạn thời gian, không có gì tự bỏ cuộc.
#:
#: 3 giây là "đủ để lấy khoá trên một hệ thống rảnh, quá ngắn để kịp gây hại
#: trên một hệ thống bận". Thà deploy đỏ ngay và thử lại lúc vắng, còn hơn
#: dừng sản xuất không rõ bao lâu.
LOCK_TIMEOUT = os.environ.get("MESFLOW_MIGRATION_LOCK_TIMEOUT", "3s")

#: Không đặt giới hạn cho THỜI GIAN CHẠY câu lệnh: một lần backfill trên bảng
#: lớn có thể chạy lâu một cách chính đáng, và cắt giữa chừng thì tệ hơn hẳn
#: chờ. Thứ cần chặn là chờ KHOÁ, không phải làm việc thật.
STATEMENT_TIMEOUT = os.environ.get("MESFLOW_MIGRATION_STATEMENT_TIMEOUT", "0")


def run_migrations_online() -> None:
    connectable = create_engine(
        SA_DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        # CỐ Ý GIỮ NGUYÊN MỘT TRANSACTION CHO CẢ CHUỖI (không bật
        # transaction_per_migration). Bật nó sẽ thu ngắn từng cửa sổ khoá,
        # nhưng đổi lại cho phép một lần nâng cấp DỪNG GIỮA CHỪNG -- mà sáu
        # lệnh seed trong repo này còn thiếu ON CONFLICT (0001, 0009, 0017,
        # 0033, 0038, 0039), nên chạy lại một chuỗi đã áp dụng một nửa sẽ hỏng.
        # Phải sửa tính idempotent của chúng TRƯỚC; cho tới lúc đó, all-or-
        # nothing + lock_timeout là đánh đổi đúng.
        with context.begin_transaction():
            # PHẢI đặt BÊN TRONG transaction của Alembic, không phải trước nó.
            # `connection.exec_driver_sql()` trên một Connection của SQLAlchemy 2.0
            # tự mở transaction ngầm; nếu chạy trước, `context.begin_transaction()`
            # thấy đã có transaction nên trở thành no-op, KHÔNG AI COMMIT, và cả
            # chuỗi migration âm thầm bị rollback khi đóng kết nối -- alembic vẫn
            # thoát mã 0. Đã dựng lại đúng ca đó: log Postgres cho thấy mọi
            # CREATE TABLE và mọi UPDATE alembic_version đều chạy, nhưng sau khi
            # xong `information_schema.tables` = 0 dòng. Một migration "thành
            # công" mà không đổi gì là kiểu hỏng tệ nhất có thể đưa vào deploy.
            connection.exec_driver_sql(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
            connection.exec_driver_sql(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
