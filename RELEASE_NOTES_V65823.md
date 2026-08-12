# MESFlow v65.8.28

## Input quantity dependency requires source session

- An operation using `input_flow_enabled` cannot start until its input source operation has at least one work session.
- If the same source is also configured as `predecessor_operation_id`, source completion is not required; an actual source session start is required instead.
- Finishing a downstream session with positive quantity now returns a clear message when the source has not reported output yet.
- Kiosk returns `DEP-409` for missing source session and `QTY-409` for missing/insufficient source quantity.
- No database migration is required.
