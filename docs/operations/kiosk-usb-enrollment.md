# Trusted M910 USB kiosk enrollment

**Acceptance limit:** the earlier PR #52 browser action remains admin-assisted:
it needs a click, a chosen Web Serial port, and an already configured ESP. The
current Issue #51 work adds an inactive M910 host provisioner library plus
firmware and server service-principal paths. It has only offline/mock and local
compile evidence so far; this work did not change or start the existing PR #53
read-only watcher and did not exercise real USB, staging API, reboot, or
heartbeat. Do not call zero-touch accepted.

The intended unattended path reuses the existing read-only M910 watcher from
PR #53 as USB hotplug detector; it does not add a second watcher or systemd
unit. The watcher/owner must integrate the `process_attached()` adapter from
`tools/m910_usb_provisioner.py` after trusted USB discovery (and its current
health check where available). The adapter opens only the supplied port,
rechecks the board HELLO against the explicit MAC/UUID manifest, and applies
the server identity checks. The provisioner does not poll or independently
discover USB ports. It sends server, Wi-Fi,
station and derived device ID only in USB maintenance on an idle, unbound board;
the board validates the same UUID/MAC and stores config with read-back and
rollback; its ordinary HTTPS connect creates/uses a PENDING identity; M910
obtains a short proof challenge, relays the board HMAC over HTTPS, and commits
the unique ID only after server approval. No UUID or kiosk token is generated
or replaced by the host. Existing ACTIVE/DISABLED/REVOKED identities and any
board with a current/alternate token, binding, offline work or active OTA fail
closed. The global legacy autobind remains disabled.

## Trust and staged configuration

- Host acceptance requires the PR #53 Espressif USB-by-id watcher plus exact
  MAC+existing UUID allowlist, unique target station entries, a verified HTTPS
  origin and CA, and 0600 manifest/token/Wi-Fi secret files. The sample TOML
  has identity, station and SSID placeholders. Do not infer these values.
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
  verified by-id MAC, CA/origin, station and Wi-Fi values. No provisioning
  service is installed/started here. USB serial is physically observable;
  local host trust and exact board allowlisting are part of the trust boundary.
- PR #53's read-only systemd service is the existing sole detector and was not
  changed by this work. Do not start a provisioning service or install udev
  rules here. PySerial uses exclusive open;
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

## Earlier admin-assisted browser flow (not unattended)

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
  service restart or deployment is part of this work.
- Prior STRICT PostgreSQL tests cover the admin USB proof/claim flow. The new
  service-principal route/migration and duplicate-MAC integration were not run
  here. Host mock/C++ suites and local M910 profile compile are in the living
  handoffs. Hardware reboot, real USB, reverse-proxy TLS and heartbeat remain
  separate release gates.

## Current implementation status (2026-11-28)

The USB backend delta is ported from PR #52 onto current MESFlow `main`
in `agent/codex/usb-enrollment-mainline` at source SHA
`4c7234eee85a8113b2468e6db138a1dfeb1cf67e`; PR #52 itself remains based on the
older PR #50 head. The deployed .396 database is at
`0057_kiosk_display_number`, so the port preserves that revision and adds USB
columns in `0058_kiosk_usb_provisioning`. Migration from an isolated database
at .396 revision 0057 to 0058 passed. Strict PostgreSQL USB/instance identity
suite plus auth/API contract tests passed 58/58; M910 host tests passed 14/14.
Preflight and the isolated official Docker/Playwright gate passed: unit
436/436 (10 skipped), static 928/928 (14 skipped), behavior 45/45 (1 skipped),
integration 638/638 (2 skipped), Playwright 607/612 (4 skipped; one flaky test
passed on retry). The service endpoints return disabled when the dedicated
credential hash is absent and still require a per-device UUID allowlist when
configured. No production database was changed.

Review found a pending kiosk could carry a non-factory `device_id` while still
having no token/station binding; USB completion previously replaced that ID.
A regression test failed on that behavior before the guard and passed after the
fix. Completion now rejects a conflicting pre-existing ID or MAC and keeps the
record PENDING. The backend remains source-only: no production migration,
deployment, USB service installation, staging provisioning, or board access.
USB auto provisioning remains OFF until staged hardware acceptance.

Firmware PR #2 is stale on 5.6.6; its source is being ported separately onto
canonical 5.6.16 as candidate 5.6.17 in
`agent/codex/esp-usb-provisioning-5616`. Never use the old PR binary. Firmware
USB provisioning remains explicit-command only, with no watcher/service; the
server service is disabled unless its dedicated token hash and exact UUID
allowlist are configured. Hardware reboot, real USB, reverse-proxy TLS and
heartbeat are release gates; no device is claimed enrolled and fleet OTA stays
OFF.
