# MESFlow v65.8.44.7

## Điều hành PO / Operation Priority
- Thêm màn **Điều hành PO** trong nhóm Điều hành.
- Xếp hạng Operation theo deadline PO, độ lệch tiến độ sản phẩm so với kế hoạch thời gian, WIP đầu vào, session đang chạy và tồn rework.
- Trạng thái: `LÀM NGAY`, `CẦN CHÚ Ý`, `ĐÚNG TIẾN ĐỘ`, `CHỜ ĐẦU VÀO`, `HOÀN THÀNH`.
- Mỗi OP hiển thị Priority Score, lý do và hành động gợi ý; score chỉ là advisory, không tự thay đổi dữ liệu sản xuất.
- WIP ưu tiên lấy từ Material Flow Ledger; nếu chưa cấu hình flow thì ước tính từ predecessor; OP đầu chuỗi dùng lượng còn lại của PO.
- Drill-down theo PO, lọc trạng thái, tìm kiếm, sort theo ưu tiên/deadline/tiến độ/mã PO.
- Auto refresh 15 giây.

Không có migration DB mới.
