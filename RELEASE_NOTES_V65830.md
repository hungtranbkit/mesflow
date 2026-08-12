# MESFlow v65.8.30

## Dashboard API theo ca

- Thêm `GET /api/dashboard/shift?shift_date=YYYY-MM-DD&shift_id=<id>`.
- Backend tự tính `range_start` và `range_end` từ cấu hình ca trong database.
- Ca qua nửa đêm được truy vấn trong một khoảng liên tục, ví dụ 18:00 ngày chọn đến 03:00 ngày hôm sau.
- Response gồm `context`, `items`, `sessions`, `activity` dùng chung một biên ca.
- Dashboard không còn gọi hai ngày rồi ghép session ở frontend.
- Sản lượng chỉ được gán cho ca chứa thời điểm báo cáo/kết thúc; thời gian session được cắt theo phần giao với các khoảng WORK.
- Các endpoint cũ `daily-progress` và `daily-sessions` vẫn tương thích, đồng thời nhận `shift_date` và `shift_id`.
