# MESFlow v65.8.11

## Hotfix Tiến trình

- Sửa PostgreSQL `GroupingError` tại API `/api/production-schedule`.
- Thêm `src.id` vào `GROUP BY` để các trường của Operation nguồn (`src.code`, `src.name`, `src.done_qty`) được chọn hợp lệ.
- Không thay đổi cấu trúc response, công thức Material Flow hoặc giao diện Gantt.
- Không cần migration database.
