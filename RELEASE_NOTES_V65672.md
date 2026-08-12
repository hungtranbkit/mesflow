# MESFlow v65.6.7.2

- Sửa lỗi Web Kiosk khi quét Operation: psycopg không thể adapt Python dict vào cột JSONB.
- Dùng `Jsonb(response)` khi ghi bảng `kiosk_idempotency` cho cả START và FINISH.
- Không cần migration database.
