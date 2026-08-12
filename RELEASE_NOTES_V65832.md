# MESFlow v65.8.32 — Session Exception Center & Overlap Guard

## Added
- Session Exception Center under Điều hành.
- Detects overlapping employee sessions, sessions open over 12 hours, long zero-quantity sessions, missing station/device, and invalid time ranges.
- Summary by severity and filters for OPEN/CLOSED sessions.
- Quick navigation back to Session Management.

## Overlap enforcement
- Start session: rejects if the employee has any overlapping session.
- Finish session: validates the final [started_at, ended_at) interval before closing.
- Supervisor edit: rejects employee/time changes that overlap another session.
- Adjacent sessions are valid when one starts exactly when the previous session ends.

## API
- GET /api/session-exceptions?status=OPEN|CLOSED&employee_id=&limit=

No database migration is required.
