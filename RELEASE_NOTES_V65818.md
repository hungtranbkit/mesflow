# MESFlow v65.8.18 — Action Log & Error Trace
- Global `X-Trace-ID` for request correlation.
- Logs user/kiosk action, API, status, duration, sanitized request/response and context.
- Stores full server traceback for unhandled errors while client receives a safe message.
- New Admin screen **Nhật ký hệ thống** with filters, detail and incident resolution notes.
- Passwords, tokens, authorization, cookies and secrets are masked.
- Migration `0016_action_error_logs` creates indexed `action_logs`.
