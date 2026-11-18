# Trusted M910 USB kiosk enrollment

**Acceptance limit:** the earlier PR #52 browser action remains admin-assisted:
it needs a click, a chosen Web Serial port, and an already configured ESP. The
current Issue #51 work adds an inactive M910 host provisioner plus firmware and
server service-principal paths. It has only offline/mock and local compile
evidence so far; no M910 service was installed or started and no real USB,
staging API, reboot, or heartbeat was exercised. Do not call zero-touch accepted.

The intended unattended path is: M910 enumerates only explicitly configured
USB VID/PID pairs; reads non-secret MAC/UUID; matches an explicit protected
allowlist; checks the target server identity state; sends server, Wi-Fi,
station and derived device ID only in USB maintenance on an idle, unbound board;
the board validates the same UUID/MAC and stores config with read-back and
rollback; its ordinary HTTPS connect creates/uses a PENDING identity; M910
obtains a short proof challenge, relays the board HMAC over HTTPS, and commits
the unique ID only after server approval. No UUID or kiosk token is generated
or replaced by the host. Existing ACTIVE/DISABLED/REVOKED identities and any
board with a current/alternate token, binding, offline work or active OTA fail
closed. The global legacy autobind remains disabled.

## Trust and staged configuration

- Host acceptance requires an exact MAC+existing UUID allowlist, unique target
  station entries, a verified HTTPS origin and CA, explicit USB VID/PID, and
  0600 manifest/token/Wi-Fi secret files. The sample TOML deliberately has
  invalid VID/PID and identity placeholders. Do not infer these values.
- Server host endpoints `/api/kiosk-provisioner/usb/{status,challenge,complete}`
  require a dedicated raw token whose SHA-256 is configured as
  `MESFLOW_KIOSK_PROVISIONER_TOKEN_SHA256`, an explicit comma-separated
  `MESFLOW_KIOSK_PROVISIONER_DEVICE_UUIDS` allowlist, and VERIFIED instance
  identity. Missing either env setting disables the flow. The token is never
  returned or audited. Challenge/completion are audited with redacted metadata.
- MAC is stored under a partial unique index when USB proof is completed. Old
  identities have no historical MAC backfill; they are never silently adopted.
- Before staged use, an authorized admin must provision the exact service token
  (raw only in a protected M910 file; SHA-256 only on server), UUID allowlist,
  verified VID/PID, CA/origin, station and Wi-Fi values. The service and sample
  unit are not installed/started here. USB serial is physically observable;
  local host trust and exact board allowlisting are part of the trust boundary.
- The source tree contains an inactive systemd example. Do not enable it or
  install udev rules until reviewed and staged. PySerial uses exclusive open;
  an advisory process lock prevents duplicate provisioner workers. Attempts
  that mutate device/server state are capped at five per UUID per hour.
- The initial USB hello is not cryptographically signed: MAC/UUID are compared
  to the trusted manifest, then the board-secret HMAC is checked during server
  enrollment after network config. Therefore the M910 port and attached ESP
  must be physically controlled; an untrusted USB device able to spoof both
  identifiers could receive the configured Wi-Fi password. If this physical
  trust boundary is insufficient, require a per-device certificate/secure
  element before enabling the host service; current firmware has no such root.

`/api/kiosk/connect` continues to deny unknown Internet clients by default;
a secret-backed first contact creates only a `PENDING` identity. The M910
service principal grants scoped proof workflow access; it is not a public
legacy autobind switch.

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

Implemented on the existing Issue #51/PR #52 backend branch and firmware PR #2
branch. Local offline tests and exact commits are recorded in each
`PROJECT_CONTEXT.md` / Issue #51. Production remains unchanged, no actual M910
host identity has been verified in this run, no real board was connected, and
the current production build does not have the new migration/routes. Strict
PostgreSQL integration, staging endpoint operation, real USB configuration,
reboot/heartbeat and unattended restart recovery remain gates. Do not claim the
new board is enrolled until authorized staged work and post-connect `ACTIVE`
evidence exist. Fleet OTA remains OFF.
