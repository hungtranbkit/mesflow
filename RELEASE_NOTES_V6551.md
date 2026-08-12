# MESFlow v65.5.1 — Admin Login Reset Fix

- Thêm CLI `python -m mesflow.cli reset-admin`.
- Thêm script `scripts/reset-admin-password.sh`.
- Reset/upsert admin trong PostgreSQL, bật lại `active=true`.
- Không tự reset mật khẩu ở mỗi lần deploy.
- Thêm `/api/system/auth-health`.
