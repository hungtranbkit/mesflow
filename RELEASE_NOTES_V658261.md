# MESFlow v65.8.28

- Preserve Flask/Werkzeug HTTP exceptions instead of converting 404/405 into HTTP 500.
- Return safe JSON for unknown routes with the original HTTP status and trace ID.
- Suppress common PHP/PHPUnit vulnerability-scanner 404 requests from Action Log by default.
- Hide historical scanner-noise entries from System Log list and statistics by default.
- Add `MESFLOW_ACTION_LOG_SCANNER_NOISE=1` to retain scanner probes when security investigation requires them.
