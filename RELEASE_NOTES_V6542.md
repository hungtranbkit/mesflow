# MESFlow v65.4.2 — Alembic psycopg v3 hotfix

- Giữ DATABASE_URL dạng `postgresql://` cho ứng dụng psycopg v3.
- Alembic tự chuyển nội bộ sang `postgresql+psycopg://`.
- Không còn yêu cầu package `psycopg2`.
- Dùng `create_engine()` trực tiếp, tránh SQLAlchemy tự chọn dialect psycopg2.
