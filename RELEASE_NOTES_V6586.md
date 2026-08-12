# MESFlow v65.8.6

## Start Production Order

- Thêm API `POST /api/production-orders/{id}/start`.
- Thêm nút Start PO tại danh sách, chi tiết và PO sắp triển khai trên Control Tower.
- PO chuyển sang `IN_PROGRESS` sau khi Start và xuất hiện ở vùng điều hành Dashboard.
- Kiosk Demo chỉ tải Operation thuộc PO `IN_PROGRESS`.
- Quét hoặc Start Session với OP của PO chưa Start sẽ bị từ chối.
- Không có migration database mới.
