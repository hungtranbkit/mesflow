# MESFlow v65.6.7.1

Hotfix lỗi API dữ liệu demo kiosk truy vấn các cột không tồn tại `parts.position` và `operations.position`.

- Đổi sắp xếp sang `parts.sort_order` và `operations.sort_order`.
- Thêm `parts.id` làm thứ tự phụ để kết quả ổn định.
- Không thay đổi database và không cần migration.
