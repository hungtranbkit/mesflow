# MESFlow 65.8.44.25

- Fix nút **Dòng vật tư** trong chi tiết PO: modal trước đây dùng sai cấu trúc `.modal`/`.modal-backdrop`, khiến lớp backdrop che nội dung và người dùng bấm như không có phản hồi.
- Hoàn thiện Material Flow theo Operation: hiển thị cấu hình nguồn đầu vào, pool GOOD/REWORK, đã cấp/còn khả dụng, đầu vào đã nhận, sản lượng/phế/rework, các OP downstream, ledger hiện tại và lịch sử audit.
- API `/api/operations/<id>/material-flow` trả thêm `relation`, `downstream`, GOOD/REWORK consumption breakdown và thông tin Part/PO để UI giải thích đầy đủ luồng vật tư.
- Modal có loading/error/retry, đóng bằng backdrop/Escape, responsive cho Full HD và màn hình nhỏ.
