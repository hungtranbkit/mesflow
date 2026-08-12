# MESFlow v65.8.33.3

- Sửa Docker test image copy thiếu `release.json` và thư mục `nginx/`.
- Đồng bộ `VERSION.txt`, `app/mesflow/__init__.py`, `release.json` và image tag trong `compose.yml`.
- Cập nhật test Dashboard đọc đúng module lịch ca hiện tại `app/mesflow/core/working_calendar.py`.
- Loại bỏ các assertion image tag khóa cứng `mesflow-app:65.8.9.1`; test dùng version hiện hành.
