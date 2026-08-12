# MESFlow v65.8.28

## Loại bỏ màn hình báo cáo Session theo Operation trùng lặp

- Gỡ mục **Báo cáo Session theo OP** khỏi menu Điều hành.
- Gỡ route và mã render giao diện `session-report`.
- Gỡ CSS chỉ dùng cho màn hình báo cáo cũ.
- Giữ **Quản lý Session** làm màn hình duy nhất để xem 50 OP gần nhất, lọc theo PO/Part/OP/công nhân, mở chi tiết session và chỉnh sửa.
- Giữ API `/api/reports/operation-sessions` để tương thích với QA Center hoặc client đang gọi trực tiếp.
- Không có migration database mới.
