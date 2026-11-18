# M910 ESP32 USB watcher — deployed canary (2026-11-18)

This service monitors physically plugged ESP32-S3 USB/JTAG devices on the trusted M910 host. It is **read-only**, does not enter USB maintenance, flash, rotate tokens, change NVS, approve enrollments or change production DB. It does **not** yet complete fully unattended enrollment. Its purpose is to establish reliable hotplug detection and safe evidence before an authenticated host-enroller is released.

## Preconditions
- M910 logged in as `mesflow`, Python 3.14+, local LAN access to ESP Web Console.
- For the first canary, MAC `84:C7:BB:79:39:6C` is explicitly allowlisted. The USB serial-by-id name and the LAN health MAC must agree. Unknown USB hardware is rejected.
- MESFlow production `MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND` stays **OFF**. Do not bypass manager/admin access or accept self-registered unknown Internet clients.

## Installed files on M910
- `~/.local/share/mesflow/esp-usb-monitor/m910_esp_usb_monitor.py`
- `~/.config/systemd/user/mesflow-esp-usb-watch.service`

## Verify
```bash
systemctl --user is-active mesflow-esp-usb-watch.service
journalctl --user -u mesflow-esp-usb-watch.service -n 20 --no-pager
python3 ~/.local/share/mesflow/esp-usb-monitor/m910_esp_usb_monitor.py --allow-mac 84:C7:BB:79:39:6C --once
```
Known expected status at first rollout: `ENROLLMENT_REQUIRED` because the board is not yet claimed by MESFlow.

## Rollback
```bash
systemctl --user disable --now mesflow-esp-usb-watch.service
```

## Remaining secure enrollment gates
1. Deploy PR #52 backend migration 0056/0057 through release gates; authorization must be granted to M910 only, not shared public access.
2. Flash and validate firmware PR #2 USB proof and commit protocol on isolated canary while preserving keypad mapping, Wi-Fi, NVS, and rollback image.
3. Implement noninteractive M910 host credential and authenticated challenge/complete adapter, without relying on expiring interactive browser cookies.
4. Verify serial proof, active claim, 200 heartbeat, token ownership, reboot persistence, and negative tests (untrusted USB, replay, revoked, duplicate ID).
5. Only then promote the watch service to provisioning mode and mark issue #51 complete.
