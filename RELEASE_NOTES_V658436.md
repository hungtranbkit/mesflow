# MESFlow v65.8.43.6

- Fix ESP32 group start/finish `invalid kiosk token` when device identity headers are missing or stale.
- Kiosk auth still prefers device_uuid/device_id, then securely falls back to the SHA-256 kiosk token hash to resolve the ACTIVE identity.
- No ESP firmware update required.
