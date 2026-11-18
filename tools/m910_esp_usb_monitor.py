"""Read-only trusted USB watcher for MESFlow ESP32 kiosks.

The watcher deliberately never enrolls/rotates credentials. The authorized
provisioning transaction is implemented in MESFlow PR #52 and requires a
separately configured authenticated host service before live activation.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

LOG = logging.getLogger("esp_m910_watch")
USB_PATTERN = re.compile(
    r"^usb-Espressif_USB_JTAG_serial_debug_unit_"
    r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})-if00$"
)
UUID_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")


@dataclass(frozen=True)
class AttachedEsp:
    port: Path
    real_device: Path
    mac: str

    @property
    def proposed_id(self) -> str:
        return "ESP32-KIOSK-" + self.mac.replace(":", "")[-4:]


def discover_usb(root: Path = Path("/dev/serial/by-id")) -> list[AttachedEsp]:
    found: list[AttachedEsp] = []
    if not root.is_dir():
        return found
    for path in sorted(root.iterdir()):
        match = USB_PATTERN.fullmatch(path.name)
        if not match or not path.is_symlink():
            continue
        real = path.resolve()
        if not re.fullmatch(r"tty(?:ACM|USB)[0-9]+", real.name):
            continue
        if not real.is_char_device():
            continue
        found.append(AttachedEsp(path, real, match.group(1).upper()))
    return found


def check_health(
    device: AttachedEsp,
    device_url: str = "http://192.168.1.254:17892",
    expected_server: str = "https://mesflow.net:443",
    timeout: float = 3.0,
) -> dict:
    """Read only. Never send commands, reset USB or expose NVS credentials."""
    if not device_url.startswith("http://"):
        raise ValueError("LAN_DEVICE_URL_MUST_BE_HTTP")
    with urlopen(device_url.rstrip("/") + "/api/device/health", timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("DEVICE_HEALTH_HTTP_ERROR")
        data = json.load(response)
    n = data.get("network") or {}
    m = data.get("mes") or {}
    h = data.get("hardware") or {}
    actual_mac = str(n.get("mac") or "").upper()
    if actual_mac != device.mac:
        raise RuntimeError("USB_VS_LAN_MAC_MISMATCH")
    if m.get("pending_transaction") or int(m.get("offline_queue") or 0) > 0:
        state = "BUSY_PRESERVE_STATE"
    elif m.get("bound") and m.get("online"):
        state = "BOUND_ONLINE"
    elif n.get("server_url") != expected_server:
        state = "SERVER_CONFIG_REQUIRED"
    elif not m.get("bound"):
        state = "ENROLLMENT_REQUIRED"
    else:
        state = "WAITING_SERVER"
    return {
        "mac": device.mac, "device_id_proposal": device.proposed_id,
        "status": state,
        "server_configured": n.get("server_url") == expected_server,
        "bound": bool(m.get("bound")), "online": bool(m.get("online")),
        "pending": bool(m.get("pending_transaction")),
        "offline_queue": int(m.get("offline_queue") or 0),
        "keypad_calibrated": bool(h.get("keypad_calibrated")),
        "firmware": str((data.get("device") or {}).get("firmware") or ""),
    }


def snapshot(root: Path, device_url: str, expected_server: str, allowed_macs: set[str]) -> list[dict]:
    results: list[dict] = []
    for esp in discover_usb(root):
        if allowed_macs and esp.mac not in allowed_macs:
            results.append({"mac": esp.mac, "status": "UNTRUSTED_USB_DENY"})
            continue
        try:
            results.append(check_health(esp, device_url, expected_server))
        except (ValueError, RuntimeError, OSError, URLError, TimeoutError) as ex:
            results.append({"mac": esp.mac, "status": "UNVERIFIED_FAIL_CLOSED",
                            "reason": type(ex).__name__})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M910 ESP32 USB monitor (no provisioning writes)")
    parser.add_argument("--by-id", type=Path, default=Path("/dev/serial/by-id"))
    parser.add_argument("--device-url", default="http://192.168.1.254:17892")
    parser.add_argument("--server-url", default="https://mesflow.net:443")
    parser.add_argument("--allow-mac", action="append", default=[])
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    allowed = {m.upper() for m in args.allow_mac}
    if args.interval < 1:
        parser.error("--interval must be >=1 second")
    last = None
    while True:
        report = snapshot(args.by_id, args.device_url, args.server_url, allowed)
        encoded = json.dumps({"devices": report, "mode": "READ_ONLY"},
                             ensure_ascii=False, sort_keys=True)
        if encoded != last:
            print(encoded, flush=True)
            last = encoded
        if not args.watch or args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
