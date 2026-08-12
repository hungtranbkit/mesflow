# MESFlow v65.8.43.3

- Fix `/api/lookup` HTTP 500 when kiosk scan event payload is a Python dict.
- Serialize `kiosk_events.payload_json` with `json.dumps(...)` before psycopg execution.
- Prevents `ProgrammingError: cannot adapt type 'dict' using placeholder '%s'`.
