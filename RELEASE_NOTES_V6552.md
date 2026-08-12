# MESFlow v65.5.2 — Admin Route Fix

- Thêm `/admin` và `/admin/`.
- Chưa đăng nhập sẽ chuyển tới `/login?next=/admin`.
- Sau đăng nhập quay lại giao diện quản trị.
- `/dashboard` và `/admin` đều dùng Web UI tại `/app`.
- Thêm `/api/system/ui-routes`.
