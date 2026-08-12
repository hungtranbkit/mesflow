# MESFlow v65.8.8

## Sửa tạo PO từ màn hình Production Order

- Thêm API riêng `/api/templates/available-for-po` trả danh sách Template active cùng số Part và Operation.
- Form **Tạo PO từ Template** ở màn hình Production Order và Control Tower dùng chung API này.
- Dropdown tự chọn Template hoàn thiện đầu tiên, hiển thị mã, tên, version, số Part và số OP.
- Có fallback về API danh sách Template cũ nếu backend chưa tải route mới.

## Template demo dễ chạy hơn

- Nâng bộ demo lên `DEMO-2.0`.
- Nút **Nạp Template demo** cập nhật lại cả Template demo cũ thay vì bỏ qua.
- Không tự tạo phụ thuộc thời gian giữa tất cả Operation khi sinh PO.
- Chỉ giữ 11 quan hệ giới hạn số lượng trên ba Template demo để kiểm thử Material Flow.
- Các Operation còn lại có thể chạy độc lập trong demo.

Không có migration database mới. PO demo đã tạo từ phiên bản cũ không tự thay đổi; dùng Force Delete rồi tạo lại từ Template demo `DEMO-2.0` để nhận cấu hình mới.
