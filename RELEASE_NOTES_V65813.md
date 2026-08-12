# MESFlow v65.8.13.1

- Thêm auto-login dành riêng cho giai đoạn test, vẫn giữ trang đăng nhập.
- Auto-login thực hiện phía server, không đưa mật khẩu admin xuống trình duyệt.
- Thêm API `/api/dashboard/daily-sessions` trả từng Work Session theo ngày.
- Khôi phục thanh thời gian 00:00–24:00 trên Dashboard.
- Mỗi thanh tương ứng một nhân viên/session, hiển thị PO, Operation, bắt đầu, kết thúc, thời lượng, đạt và lỗi.
- Session đang mở tự cập nhật thời lượng mỗi 10 giây.

Trước khi production: `MESFLOW_TEST_AUTO_LOGIN=0`.
