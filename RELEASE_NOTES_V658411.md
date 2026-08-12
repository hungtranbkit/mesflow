# MESFlow v65.8.41.1

- Sửa QR Print Center không render sau khi API trả dữ liệu.
- Chuẩn hóa response QR và loại bỏ phụ thuộc DOM/global helper không ổn định.
- Tách Nhật ký hệ thống sang `pages/system-logs.js`.
- Sửa lỗi ReferenceError do dùng biến DOM tự sinh từ thuộc tính `id`.
- Thêm loading/error state và regression test cho QR/System Logs.
