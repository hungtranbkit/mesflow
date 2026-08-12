# MESFlow v65.8.43.2

## Kiosk HTTP compatibility

- Allow plain HTTP on port 80 for ESP32 device API routes:
  - `/api/kiosk/*`
  - `/api/station/*`
  - `/api/lookup`
  - `/api/session/group/*`
  - `/api/demo-codes`
- All other HTTP traffic still redirects to HTTPS.
- This avoids HTTP 301 responses for ESP32 firmware using `http://mesflow.net`.
