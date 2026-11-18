"""Read-only trusted USB watcher for MESFlow ESP32 kiosks.

The watcher deliberately never enrolls/rotates credentials. The authorized
provisioning transaction is implemented in MESFlow PR #52 and requires a
separately configured authenticated host service before live activation.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

LOG = logging.getLogger("esp_m910_watch")
STAGED_HEALTH_ORIGIN = "http://192.168.1.254:17892"
HEALTH_MAX_BYTES = 32 * 1024
USB_PATTERN = re.compile(
    r"^usb-Espressif_USB_JTAG_serial_debug_unit_"
    r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})-if00$"
)
UUID_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(url, timeout=3.0):
    """Open health HTTP without following redirects to arbitrary LAN hosts."""
    return build_opener(_NoRedirect()).open(url, timeout=timeout)


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
        raw = response.read(HEALTH_MAX_BYTES + 1)
        if len(raw) > HEALTH_MAX_BYTES:
            raise RuntimeError("HEALTH_BODY_TOO_LARGE")
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("DEVICE_HEALTH_INVALID_JSON")
    n = data.get("network") or {}
    m = data.get("mes") or {}
    h = data.get("hardware") or {}
    d = data.get("device") or {}
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
        "firmware": str(d.get("firmware") or ""),
        "firmware_version": str(d.get("firmware_version") or ""),
        "firmware_build": str(d.get("firmware_build") or ""),
        "usb_provision_protocol": str(d.get("usb_provision_protocol") or ""),
        "hardware_model": str(d.get("hardware_model") or ""),
    }


PROVISIONABLE_HEALTH_STATES = {"SERVER_CONFIG_REQUIRED", "ENROLLMENT_REQUIRED"}


def _bundle_manifest() -> dict:
    candidates = (Path(__file__).with_name("m910_usb_bundle_manifest.json"),
                  Path(__file__).resolve().parent.parent / "manifest.json")
    for path in candidates:
        if path.is_file():
            with path.open(encoding="utf-8") as stream:
                value = json.load(stream)
            if isinstance(value, dict) and value.get("version"):
                return value
    raise ValueError("BUNDLE_MANIFEST_MISSING")


def _load_provisioner_module():
    """Load the bundled adapter only when explicit staged mode is enabled."""
    try:
        return importlib.import_module("m910_usb_provisioner")
    except ModuleNotFoundError as exc:
        if exc.name != "m910_usb_provisioner":
            raise
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        return importlib.import_module("m910_usb_provisioner")


def _candidate_target(staged_provisioner, mac: str):
    return next((target for target in staged_provisioner.config.devices
                 if target.mac_address == mac), None)


def snapshot(root: Path, device_url: str, expected_server: str, allowed_macs: set[str],
             *, staged_provisioner=None) -> list[dict]:
    results: list[dict] = []
    for esp in discover_usb(root):
        if (allowed_macs and esp.mac not in allowed_macs) or (
                staged_provisioner is not None and
                _candidate_target(staged_provisioner, esp.mac) is None):
            results.append({"mac": esp.mac, "status": "UNTRUSTED_USB_DENY"})
            continue
        try:
            if staged_provisioner is not None:
                endpoint = _bundle_manifest().get("lan_health_endpoint", "")
                parsed = urlsplit(endpoint)
                manifest_origin = f"{parsed.scheme}://{parsed.netloc}"
                if (endpoint != STAGED_HEALTH_ORIGIN + "/api/device/health" or
                        manifest_origin != STAGED_HEALTH_ORIGIN or
                        device_url.rstrip("/") != manifest_origin):
                    results.append({"mac": esp.mac, "status": "STAGED_DEVICE_ENDPOINT_DENY"})
                    continue
            health = check_health(esp, device_url, expected_server)
            if staged_provisioner is None:
                results.append(health)
                continue

            if staged_provisioner.config.base_url != expected_server.rstrip("/"):
                results.append({"mac": esp.mac, "status": "STAGED_ORIGIN_MISMATCH"})
                continue
            firmware = _bundle_manifest().get("firmware", {})
            build_pattern = firmware.get("required_build_pattern")
            if (str(health.get("firmware_version") or "") != firmware.get("required_version") or
                    not build_pattern or
                    not re.fullmatch(build_pattern, str(health.get("firmware_build") or "")) or
                    health.get("usb_provision_protocol") != firmware.get("protocol") or
                    health.get("hardware_model") != firmware.get("hardware_model")):
                results.append({"mac": esp.mac, "status": "FIRMWARE_INCOMPATIBLE"})
                continue
            target = _candidate_target(staged_provisioner, esp.mac)
            health_state = str(health.get("status") or "").upper()
            if health_state not in PROVISIONABLE_HEALTH_STATES | {"BOUND_ONLINE"}:
                results.append(health)
                continue
            health_bound_online = health.get("bound") is True and health.get("online") is True
            if (str(health.get("mac") or "").upper() != target.mac_address or
                    (health_state in PROVISIONABLE_HEALTH_STATES and
                     (health.get("bound") is not False or health.get("online") is not False)) or
                    (health_state == "BOUND_ONLINE" and not health_bound_online)):
                results.append({"mac": esp.mac, "status": "LAN_STATE_NOT_ELIGIBLE"})
                continue

            phase = _load_provisioner_module().process_attached(
                staged_provisioner, str(esp.port))
            # The server's ACTIVE response means claim accepted. Report ACTIVE
            # only after the independent LAN heartbeat proves bound+online.
            if phase == "active" and health_state != "BOUND_ONLINE":
                phase = "awaiting-active"
            results.append({**health, "provisioning_phase": phase})
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
    parser.add_argument("--enable-staged-provisioning", action="store_true",
                        help="explicitly enable staged USB enrollment mutations")
    parser.add_argument("--provisioner-config", type=Path,
                        help="0600 staged manifest; no effect without the explicit enable flag")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    allowed = {m.upper() for m in args.allow_mac}
    if args.interval < 1:
        parser.error("--interval must be >=1 second")
    if args.provisioner_config and not args.enable_staged_provisioning:
        parser.error("--provisioner-config requires --enable-staged-provisioning")
    if args.enable_staged_provisioning and not args.provisioner_config:
        parser.error("--enable-staged-provisioning requires --provisioner-config")

    staged_provisioner = None
    state = None
    if args.enable_staged_provisioning:
        adapter = _load_provisioner_module()
        config = adapter.load_config(args.provisioner_config)
        if config.base_url != args.server_url.rstrip("/"):
            parser.error("provisioner origin must match --server-url")
        api = adapter.ProvisionerAPI(config)
        state = adapter.StateStore(config.state_db)
        staged_provisioner = adapter.Provisioner(config, api=api, state=state)

    try:
        last = None
        while True:
            report = snapshot(args.by_id, args.device_url, args.server_url, allowed,
                              staged_provisioner=staged_provisioner)
            encoded = json.dumps({"devices": report,
                                  "mode": "STAGED_OPT_IN" if staged_provisioner else "READ_ONLY"},
                                 ensure_ascii=False, sort_keys=True)
            if encoded != last:
                print(encoded, flush=True)
                last = encoded
            if not args.watch or args.once:
                break
            time.sleep(args.interval)
        return 0
    finally:
        if state is not None:
            state.close()


if __name__ == "__main__":
    raise SystemExit(main())
