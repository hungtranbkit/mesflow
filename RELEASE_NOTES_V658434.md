# MESFlow v65.8.43.4

- Kiosk telemetry compatibility: `/api/kiosk/events` accepts `client_event_id`/`device_id` from ESP firmware as aliases for `event_uuid`/`device_uuid`.
- Preserve legacy telemetry envelope fields inside `payload_json`.
- System Logs: Action Log and Error Trace details expand inline immediately below the selected row; selecting another row closes the previous detail.
- Keeps web/non-kiosk HTTPS behavior unchanged.
