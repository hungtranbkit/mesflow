# MESFlow v65.8.7

## Tạo Production Order từ Template

- Production Order mới bắt buộc chọn Template nguồn.
- Khi tạo PO, hệ thống sao chép toàn bộ Part, Operation, thời gian chuẩn, thiết bị, phụ thuộc tuần tự và quan hệ dòng vật liệu từ Template.
- PO lưu `source_template_id`, mã Template và version Template để truy vết.
- Sau khi sao chép, PO là bản độc lập và có thể override mà không sửa Template.
- API tạo PO rỗng bị khóa; POST `/api/production-orders` chỉ chấp nhận khi có `template_id`.
- Import Operation không còn tự sinh PO rỗng; PO phải được tạo từ Template trước.
- Sau khi tạo thành công, giao diện tự mở PO mới và hiển thị số Part/Operation đã sao chép.
- PO ở trạng thái PLANNED có nút Start PO; sau Start, Operation xuất hiện trong Kiosk Demo và PO xuất hiện trên Control Tower.

## Database

- Migration `0015_po_template_source`.
