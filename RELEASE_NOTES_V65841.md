# MESFlow v65.8.41

- Thêm popup Dòng vật tư trong chi tiết Operation.
- Hiển thị Nguồn → Đích → Session → số lượng → thời gian, tổng sản xuất/phân bổ/còn lại.
- Phân loại ledger RUNTIME, BACKFILL và ADMIN_EDIT.
- Thêm lịch sử UPDATE/DELETE ledger bằng PostgreSQL trigger.
- Chặn xóa Operation/Part/PO khi đã có Session hoặc ledger.
- Chặn đổi OP nguồn khi đã phát sinh tiêu thụ.
- Chặn giảm sản lượng nguồn thấp hơn lượng đã phân bổ.
- Chặn Excel Replace khi đã có dữ liệu thực thi; bảo vệ Merge khỏi đổi cấu trúc hoặc giảm nguồn sai.
