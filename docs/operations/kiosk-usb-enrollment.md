# Trusted USB kiosk enrollment

This workflow replaces per-device manual approval for a physically attached,
new ESP32. It does not enable legacy/global autobind. `/api/kiosk/connect`
continues to deny unknown clients that do not present a device secret; a
secret-backed first contact creates only a `PENDING` identity.

## Flow

1. The ESP retries its normal HTTPS connection and appears as `PENDING` with
   the requested station. The authenticated MESFlow admin opens Kiosk
   Management and selects **Nạp tự động qua USB** on that exact UUID.
2. Chrome/Edge USB Serial permission requires choosing the connected device.
   Firmware enters the existing USB maintenance mode only from an idle screen.
3. MESFlow issues a random 120-second challenge bound to the pending UUID,
   station and admin. Firmware returns a USB-only HMAC-SHA256 proof using
   `SHA256(device_secret)`; neither the secret nor kiosk token is sent to the
   browser. The signed message also binds MAC, derived ID and firmware version.
4. MESFlow checks the proof, current instance identity, station, unique
   `ESP32-KIOSK-{last four MAC hex}` ID, no prior token/station binding, and
   PENDING status. The transaction writes an audit record and opens one
   15-minute claim window. It leaves the identity PENDING and returns no token.
5. After server approval, firmware commits only `mesflow_cfg/device_id` with
   read-back and restore-on-write-failure. Its normal HTTPS retry claims the
   token once. UI reports ACTIVE only after the management API confirms it.

All browser endpoints require an authenticated `admin` and a VERIFIED instance.
Challenge/proof material is not written to logs/audit. The firmware redacts
both USB commands from serial RX logs. Maintenance proof/commit commands are
accepted only in maintenance while the device is unbound, enrollment-pending,
idle, without a pending transaction or offline events. Wi-Fi, station, server,
UUID, secret, kiosk token, offline journal and OTA settings are not changed.

## Recovery and gates

- A rejected proof or failed API call makes no server approval. Before server
  approval, firmware does not change NVS. A failed local ID write restores the
  previous value. An approved but unclaimed window expires after 15 minutes;
  the identity remains PENDING and no token is returned to the admin.
- Existing ACTIVE/DISABLED identities and identities with a prior token or
  station binding are refused, including status changes back to PENDING.
  Duplicate IDs are serialized by an advisory transaction lock and rejected.
- No production manual-DB mutation, global `MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND`,
  service restart or deployment is part of this workflow.
- Local STRICT PostgreSQL integration exercises proof/claim/idempotency,
  invalid proof, anonymous denial, disabled/prior-bound refusal, unique ID
  collision, token ownership and heartbeat. Host C++ tests exercise firmware
  eligibility/command policy and MAC-derived IDs. Hardware reboot, real USB,
  reverse-proxy TLS and live production heartbeat remain separate release gates.

## Current implementation status (2026-11-18)

Implemented on the Issue #51 branch stacked on MESFlow PR #50 and the scoped
firmware PR #2 branch. Local test results and exact commits are recorded in
`PROJECT_CONTEXT.md` / the Issue #51 update. Production still runs the older
MESFlow build without migrations 0056/0057 or these endpoints; do not claim the
new board is enrolled until an authorized rollout and post-connect `ACTIVE`
evidence exist. Fleet OTA remains OFF.
