# MESFlow 65.8.44.10

- Sửa màn Lịch làm việc: nhãn giờ của start_minute/end_minute cập nhật tức thời khi chỉnh số phút.
- Đổi Bắt đầu/Kết thúc ca sẽ đồng bộ mép đầu/cuối của các khoảng WORK thay vì để hai bộ thời gian lệch nhau.
- Ca qua nửa đêm tự quy đổi giờ kết thúc sang +1 ngày khi cần.
- Thêm khoảng mới dựa trên mốc kết thúc gần nhất thay vì luôn hard-code 08:00–12:00.
- Timeline Dashboard tiếp tục đọc trực tiếp intervals đã lưu, nên sau lưu/reload các mốc giờ phản ánh cấu hình mới.
- Đồng bộ version metadata lên 65.8.44.10.
