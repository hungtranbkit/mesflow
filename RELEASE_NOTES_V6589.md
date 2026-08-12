# MESFlow v65.8.9.1

## Scanner error codes
- Kiosk displays a stable error code, message and corrective action.
- Standard codes include SCN-001/002/003/004, EMP-001, OP-001, PO-001, SES-409, QTY-409, NET-001 and SYS-500.
- API responses preserve `error_code` and `action` so ESP/web kiosks can show the same guidance.

## Timezone consistency
- Database connections run in UTC.
- Web UI and kiosk clock explicitly render `Asia/Ho_Chi_Minh` (UTC+7), independent of browser/server timezone.
- `datetime-local` PO schedule values are interpreted as Ho Chi Minh City time and converted to UTC before sending.
- Docker services receive `TZ=Asia/Ho_Chi_Minh`; PostgreSQL client timezone remains UTC.
