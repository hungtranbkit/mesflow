# MESFlow v65.8.43.5

- Fix ESP32 v5.x kiosk token verification when firmware sends stable `device_uuid` plus display `device_id`.
- Legacy kiosk auth now prefers `X-Device-UUID`/`device_uuid` and falls back to `X-Device-ID`/`device_id`.
- Apply the same identity resolution to group start, group finish, heartbeat and offline event sync.
- Add `/api/kiosk/connect` alias for ESP32 runtime bind flow.
- New binds prefer immutable `device_uuid` as the identity key.
