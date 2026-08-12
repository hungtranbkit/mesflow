# MESFlow v65.8.38 — Action Log / Error Trace Retention

- Thêm migration `0020_log_retention` với `error_traces` và lịch sử `log_retention_runs`.
- Ghi Error Trace riêng cho lỗi HTTP 500 hoặc exception chưa xử lý.
- Chính sách mặc định: SUCCESS 30 ngày, SLOW 90 ngày, lỗi đã xử lý 180 ngày, lỗi chưa xử lý và security 365 ngày.
- Error Trace đã xử lý 180 ngày, chưa xử lý 365 ngày.
- Xóa theo batch cấu hình, có preview/dry-run và API Admin.
- Thêm `scripts/cleanup-logs.sh` và trình cài cron hàng ngày.
