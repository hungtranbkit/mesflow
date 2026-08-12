# MESFlow v65.6.8.1 — Deploy consistency fix

- Đồng bộ image tag Compose với runtime/version: 65.6.8.1.
- Sửa preflight/backup dùng đúng thư mục PostgreSQL `runtime/postgres-v65`.
- Preflight báo rõ khi thiếu certificate Nginx thay vì để container nginx khởi động thất bại.
- Thêm `pytest.ini` để test tìm đúng package trong thư mục `app`.
- Loại bỏ cache Python/pytest khỏi gói phát hành.
