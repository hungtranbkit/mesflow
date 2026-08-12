# MESFlow v65.8.39.1

- Sửa migration 0019 thất bại vì revision ID dài hơn `alembic_version.version_num VARCHAR(32)`.
- Migration 0019 mở rộng cột version lên `VARCHAR(128)` trước khi Alembic ghi revision mới.
- Bổ sung test tĩnh và PostgreSQL integration để ngăn lỗi revision quá dài tái diễn.
- Không đổi revision ID, không cần stamp thủ công và không làm mất dữ liệu.
