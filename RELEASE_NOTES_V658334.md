# MESFlow v65.8.33.4

## Dashboard route contract test hotfix

- Sửa test `test_shift_dashboard_backend_contract` để kiểm tra đúng cách Flask ghép URL từ Blueprint `url_prefix=/api` và route `/dashboard/shift`.
- Không còn yêu cầu chuỗi literal `/api/dashboard/shift` phải xuất hiện nguyên vẹn trong `analytics.py`.
- Đồng bộ VERSION.txt, runtime version, release.json và compose image tag.
