# MESFlow v65.8.44.11

- Thiết kế lại giao diện Sửa ca: người dùng nhập giờ HH:mm trực tiếp, không còn thấy start_minute/end_minute kiểu 480/720.
- Đổi Mục tiêu (phút) thành Giờ công mục tiêu (ví dụ 8 giờ), backend vẫn lưu target_minutes để tương thích dữ liệu cũ.
- Tự nhận biết ca qua nửa đêm từ giờ bắt đầu/kết thúc; không cần thao tác checkbox kỹ thuật.
- Khoảng thời gian hiển thị theo cột Loại / Từ / Đến / Ghi chú, responsive cho mobile.
- Giữ nguyên schema và API; không cần migration.
