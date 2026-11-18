import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watcher = _load("m910_esp_usb_monitor", ROOT / "tools/m910_esp_usb_monitor.py")
provisioner_module = _load("m910_usb_provisioner", ROOT / "tools/m910_usb_provisioner.py")

MAC = "84:C7:BB:79:39:6C"
UUID = "fc0c33a9-2f76-424f-a256-217699b57712"
SERVER = "https://mesflow.example:443"
STATION = "LASER-01"
SSID = "Test-Network"
FW_BUILD = "20261112.0003.g2fcafb2db5"
FW_PROTOCOL = "MESFLOW-KIOSK-USB-ENROLLMENT-V1"
FW_MODEL = "ES3C28P"


def _firmware_fields():
    return {"firmware_version": "5.6.6", "firmware_build": FW_BUILD,
            "usb_provision_protocol": FW_PROTOCOL, "hardware_model": FW_MODEL}


class FakeAPI:
    def __init__(self):
        self.state = {"status": "PENDING", "provisionable": True,
                      "enrollment_window_open": False, "station_code": STATION}
        self.calls = []

    def status(self, device_uuid):
        self.calls.append(("status", device_uuid))
        return dict(self.state)

    def challenge(self, device_uuid):
        self.calls.append(("challenge", device_uuid))
        return {"challenge": "c" * 64}

    def complete(self, proof):
        self.calls.append(("complete", dict(proof)))
        self.state = {"status": "PENDING", "provisionable": True,
                      "enrollment_window_open": True, "station_code": STATION}
        return {"approved": True, "device_id": "ESP32-KIOSK-396C"}


class FakeHTTPResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, limit=-1):
        return self.payload[:limit] if limit >= 0 else self.payload


class FakeHTTPSProvisioner:
    """In-process HTTPS endpoint double; it never opens a socket."""
    def __init__(self):
        self.requests = []
        self.state = {"status": "PENDING", "provisionable": True,
                      "enrollment_window_open": False, "station_code": STATION,
                      "device_id": "ESP32-KIOSK-396C", "mac_address": MAC}

    def open(self, request, timeout):
        headers = {k.lower(): v for k, v in request.header_items()}
        body = request.data.decode() if request.data else ""
        path = request.full_url.removeprefix(SERVER)
        self.requests.append({"method": request.get_method(), "url": request.full_url,
                              "path": path, "headers": headers, "body": body,
                              "timeout": timeout})
        assert request.full_url.startswith("https://")
        assert headers.get("x-mesflow-provisioner") == "test-only-not-for-live"
        if request.get_method() == "GET" and path.startswith("/api/kiosk-provisioner/usb/status?"):
            assert f"device_uuid={UUID}" in path
            return FakeHTTPResponse(self.state)
        payload = json.loads(body)
        if path == "/api/kiosk-provisioner/usb/challenge":
            assert payload == {"device_uuid": UUID}
            return FakeHTTPResponse({"challenge": "c" * 64})
        if path == "/api/kiosk-provisioner/usb/complete":
            assert payload["device_uuid"] == UUID
            assert payload["mac_address"] == MAC
            assert payload["station_code"] == STATION
            assert payload["device_id"] == "ESP32-KIOSK-396C"
            assert payload["proof"] == "a" * 64
            self.state["enrollment_window_open"] = True
            return FakeHTTPResponse({"approved": True, "device_id": "ESP32-KIOSK-396C"})
        raise AssertionError(f"unexpected fake HTTPS request {request.get_method()} {path}")


class FakeTransport:
    def __init__(self, *, mac=MAC, firmware_fields=None):
        self.mac = mac
        self.firmware_fields = firmware_fields or _firmware_fields()
        self.commands = []
        self.timeouts = []
        self.closed = False

    def close(self):
        self.closed = True

    def command(self, line, *, marker, timeout):
        self.commands.append(line.split(" ", 1)[0])
        self.timeouts.append(timeout)
        if line == "usb-provision-hello":
            # HELLO is deliberately unsigned: the later challenge proof is the
            # cryptographic device-authentication step, not this identity hint.
            return "MESFLOW_USB_HELLO:" + json.dumps({
                "device_uuid": UUID, "mac_address": self.mac,
                "device_id": "ESP32-KIOSK-396C", "station_code": STATION,
                "server_url": SERVER, "wifi_ssid": SSID, "bound": False,
                "credential_present": False, "idle": True,
                "pending_transaction": False, "queued_events": False,
                "ota_in_progress": False, **self.firmware_fields,
            })
        if line == "maintenance confirm":
            return "[MAINT] USB maintenance confirm"
        if line.startswith("usb-provision-proof "):
            challenge = line.rsplit(" ", 1)[1]
            return "MESFLOW_USB_PROOF:" + json.dumps({
                "device_uuid": UUID, "challenge": challenge, "mac_address": MAC,
                "device_id": "ESP32-KIOSK-396C", "station_code": STATION,
                "firmware_version": "5.6.6", "proof": "a" * 64,
            })
        if line == "usb-provision-commit ESP32-KIOSK-396C":
            return "[USB-PROVISION] DEVICE_ID_SAVED ESP32-KIOSK-396C"
        if line == "maintenance exit":
            return "[MAINT] EXIT"
        raise AssertionError(f"unexpected command {line.split(' ', 1)[0]}")


def _make_provisioner(tmp_path, api):
    target = provisioner_module.DeviceTarget(MAC, UUID, STATION, SSID,
                                               str(tmp_path / "wifi.secret"))
    config = provisioner_module.ProvisionerConfig(
        SERVER, "unused-token-file", "unused-ca-file", str(tmp_path / "state.sqlite3"),
        115200, 5, (target,))
    state = provisioner_module.StateStore(config.state_db)
    return provisioner_module.Provisioner(config, api=api, state=state)


def _attached(mac=MAC):
    return watcher.AttachedEsp(Path(f"/dev/serial/by-id/usb-{mac}"),
                               Path("/dev/ttyACM0"), mac)


def test_read_only_default_does_not_open_serial_for_enrollment_candidate(monkeypatch):
    attached = _attached()
    opened = []
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False, "online": False,
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport",
                        lambda *_a, **_k: opened.append(True))

    result = watcher.snapshot(Path("/dev/serial/by-id"), "http://device", SERVER, {MAC})

    assert result[0]["status"] == "ENROLLMENT_REQUIRED"
    assert opened == []


def test_cli_manifest_alone_cannot_enable_mutations(capsys):
    with pytest.raises(SystemExit) as err:
        watcher.main(["--once", "--provisioner-config", "/path/that/must/not/be/read"])

    assert err.value.code == 2
    assert "requires --enable-staged-provisioning" in capsys.readouterr().err


def test_unknown_mac_is_denied_before_lan_or_serial(monkeypatch, tmp_path):
    attached = _attached("02:00:00:00:00:01")
    api = FakeAPI()
    provisioner = _make_provisioner(tmp_path, api)
    lan_calls = []
    serial_calls = []
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_a: lan_calls.append(True))
    monkeypatch.setattr(provisioner_module, "SerialTransport",
                        lambda *_a, **_k: serial_calls.append(True))

    result = watcher.snapshot(Path("/dev/serial/by-id"), "http://device", SERVER, set(),
                              staged_provisioner=provisioner)

    assert result[0]["status"] == "UNTRUSTED_USB_DENY"
    assert lan_calls == serial_calls == api.calls == []


def test_integrated_flow_runs_after_lan_gate_and_never_calls_active_on_claim(monkeypatch, tmp_path):
    attached = _attached()
    events = []
    api = FakeAPI()
    transport = FakeTransport()
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: (
        events.append("lan-gate") or {"mac": MAC, "status": "ENROLLMENT_REQUIRED",
                                      "bound": False, "online": False, **_firmware_fields()}))
    monkeypatch.setattr(provisioner_module, "SerialTransport",
                        lambda port, baud: (events.append("serial-open") or transport))

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert events.index("lan-gate") < events.index("serial-open")
    assert [call[0] for call in api.calls] == ["status", "challenge", "complete"]
    proof = api.calls[-1][1]
    assert (proof["device_uuid"], proof["mac_address"], proof["station_code"]) == (UUID, MAC, STATION)
    assert result[0]["provisioning_phase"] == "awaiting-active"
    assert result[0]["status"] != "BOUND_ONLINE"
    assert max(transport.timeouts) <= 10
    assert transport.closed


def test_usb_hello_spoof_fails_closed_after_lan_mac_match(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    transport = FakeTransport(mac="02:00:00:00:00:01")
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False, "online": False,
        **_firmware_fields(),
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["provisioning_phase"] == "identity-mismatch"
    assert api.calls == []
    assert transport.commands == ["usb-provision-hello"]


def test_usb_hello_firmware_capability_must_match_bundle_before_api(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    transport = FakeTransport(firmware_fields={
        **_firmware_fields(), "usb_provision_protocol": "unsupported-protocol"})
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False,
        "online": False, **_firmware_fields(),
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER,
                              {MAC}, staged_provisioner=provisioner)

    assert result[0]["provisioning_phase"] == "firmware-incompatible"
    assert api.calls == []
    assert transport.commands == ["usb-provision-hello"]


def test_only_lan_bound_online_plus_server_active_can_report_active(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    api.state = {"status": "ACTIVE", "device_id": "ESP32-KIOSK-396C",
                 "station_code": STATION}
    transport = FakeTransport()
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "BOUND_ONLINE", "bound": True, "online": True,
        **_firmware_fields(),
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["provisioning_phase"] == "active"


def test_server_active_without_lan_heartbeat_stays_awaiting_active(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    api.state = {"status": "ACTIVE", "device_id": "ESP32-KIOSK-396C",
                 "station_code": STATION}
    transport = FakeTransport()
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False, "online": False,
        **_firmware_fields(),
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["provisioning_phase"] == "awaiting-active"


def test_firmware_outside_bundle_compatibility_is_denied_before_serial(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    provisioner = _make_provisioner(tmp_path, api)
    opened = []
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False,
        "online": False, **{**_firmware_fields(), "firmware_version": "5.6.5"},
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport",
                        lambda *_a, **_k: opened.append(True))

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["status"] == "FIRMWARE_INCOMPATIBLE"
    assert opened == []
    assert api.calls == []


def test_wrong_firmware_build_identity_is_denied_before_serial(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    provisioner = _make_provisioner(tmp_path, api)
    opened = []
    health = {"mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False,
              "online": False, **{**_firmware_fields(), "firmware_build": "unverified-build"}}
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: health)
    monkeypatch.setattr(provisioner_module, "SerialTransport",
                        lambda *_a, **_k: opened.append(True))

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["status"] == "FIRMWARE_INCOMPATIBLE"
    assert opened == [] and api.calls == []


def test_staged_health_url_is_pinned_and_never_queried_for_arbitrary_host(monkeypatch, tmp_path):
    attached = _attached()
    api = FakeAPI()
    provisioner = _make_provisioner(tmp_path, api)
    health_calls = []
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args, **_kwargs: health_calls.append(True))

    result = watcher.snapshot(Path("/dev/serial/by-id"), "http://evil.example:8080", SERVER,
                              {MAC}, staged_provisioner=provisioner)

    assert result[0]["status"] == "STAGED_DEVICE_ENDPOINT_DENY"
    assert health_calls == []


@pytest.mark.parametrize("status", ["DISABLED", "REVOKED", "SUSPENDED"])
def test_non_pending_server_identity_is_never_claimed_or_reconfigured(
        monkeypatch, tmp_path, status):
    attached = _attached()
    api = FakeAPI()
    api.state = {"status": status, "provisionable": False,
                 "device_id": "ESP32-KIOSK-396C", "station_code": STATION}
    transport = FakeTransport()
    provisioner = _make_provisioner(tmp_path, api)
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: {
        "mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False,
        "online": False, **_firmware_fields(),
    })
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    result = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)

    assert result[0]["provisioning_phase"] == "ineligible"
    assert api.calls == [("status", UUID)]
    assert transport.commands == ["usb-provision-hello"]


def test_mutation_budget_is_bounded_and_state_contains_no_secrets(tmp_path):
    target = provisioner_module.DeviceTarget(MAC, UUID, STATION, SSID,
                                               "do-not-read-this-in-test")
    state = provisioner_module.StateStore(tmp_path / "state.sqlite3")

    assert [state.allow_mutation(target, 3) for _ in range(4)] == [True, True, True, False]
    encoded_state = json.dumps(state.snapshot())
    assert '"failures": 3' in encoded_state
    assert "do-not-read-this-in-test" not in encoded_state


def test_process_lock_prevents_duplicate_runtime_instance(tmp_path):
    lock_path = tmp_path / "locks" / "m910.lock"
    with provisioner_module.ProcessLock(lock_path):
        with pytest.raises(provisioner_module.ProvisionerError, match="another_provisioner"):
            with provisioner_module.ProcessLock(lock_path):
                pass


def test_untrusted_server_error_code_is_redacted_before_audit(tmp_path, caplog):
    caplog.set_level("INFO", logger="m910-kiosk-provisioner")
    class RejectedHTTPS:
        def open(self, *_args, **_kwargs):
            return FakeHTTPResponse({"ok": False, "code": "credential leaked: test-only-not-for-live"})

    config = provisioner_module.ProvisionerConfig(
        SERVER, "unused", "/etc/ssl/certs/ca-certificates.crt",
        str(tmp_path / "state.sqlite3"), 115200, 5,
        (provisioner_module.DeviceTarget(MAC, UUID, STATION, SSID,
                                         str(tmp_path / "wifi.secret")),))
    api = provisioner_module.ProvisionerAPI(
        config, token="test-only-not-for-live", opener=RejectedHTTPS())
    state = provisioner_module.StateStore(config.state_db)
    provisioner = provisioner_module.Provisioner(config, api=api, state=state)

    phase = provisioner.process(config.devices[0], FakeTransport())

    assert phase == "blocked"
    assert "api_rejected" in caplog.text
    assert "test-only-not-for-live" not in caplog.text


def test_api_can_use_local_fake_https_transport_without_live_network(tmp_path):
    config = provisioner_module.ProvisionerConfig(
        SERVER, "unused", "/etc/ssl/certs/ca-certificates.crt",
        str(tmp_path / "state.sqlite3"), 115200, 5, ())
    opener = object()

    api = provisioner_module.ProvisionerAPI(
        config, token="test-only-not-for-live", opener=opener)

    assert api._opener is opener


def test_serial_open_requests_exclusive_mode_and_bounded_io(monkeypatch):
    observed = {}

    class FakeSerial:
        def __init__(self, *args, **kwargs):
            observed.update(kwargs)

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=FakeSerial))
    provisioner_module.SerialTransport("/dev/ttyTEST", 115200)

    assert observed == {"baudrate": 115200, "timeout": 0.2,
                        "write_timeout": 1, "exclusive": True}


def test_real_api_client_fake_https_and_fake_usb_lifecycle_with_heartbeat_gate(
        monkeypatch, tmp_path):
    attached = _attached()
    http = FakeHTTPSProvisioner()
    config = provisioner_module.ProvisionerConfig(
        SERVER, "unused", "/etc/ssl/certs/ca-certificates.crt",
        str(tmp_path / "state.sqlite3"), 115200, 5,
        (provisioner_module.DeviceTarget(MAC, UUID, STATION, SSID,
                                         str(tmp_path / "wifi.secret")),))
    api = provisioner_module.ProvisionerAPI(
        config, token="test-only-not-for-live", opener=http)
    state = provisioner_module.StateStore(config.state_db)
    provisioner = provisioner_module.Provisioner(config, api=api, state=state)
    transport = FakeTransport()
    health = {"mac": MAC, "status": "ENROLLMENT_REQUIRED", "bound": False,
              "online": False, **_firmware_fields()}
    monkeypatch.setattr(watcher, "discover_usb", lambda _root: [attached])
    monkeypatch.setattr(watcher, "check_health", lambda *_args: dict(health))
    monkeypatch.setattr(provisioner_module, "SerialTransport", lambda *_a, **_k: transport)

    first = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                             staged_provisioner=provisioner)
    assert first[0]["provisioning_phase"] == "awaiting-active"
    assert [r["path"].split("?", 1)[0] for r in http.requests] == [
        "/api/kiosk-provisioner/usb/status",
        "/api/kiosk-provisioner/usb/challenge",
        "/api/kiosk-provisioner/usb/complete",
    ]
    assert all(r["url"] == SERVER + r["path"] and r["timeout"] == 8
               for r in http.requests)
    assert "test-only-not-for-live" not in json.dumps(first)
    assert "a" * 64 not in json.dumps(first)

    # Replug/restart retry is idempotent: the approval window causes only the
    # existing device_id commit, not a second claim or a new identity.
    state.close()
    state = provisioner_module.StateStore(config.state_db)
    provisioner = provisioner_module.Provisioner(config, api=api, state=state)
    transport = FakeTransport()
    second = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                              staged_provisioner=provisioner)
    assert second[0]["provisioning_phase"] == "awaiting-active"
    assert [r["method"] for r in http.requests].count("POST") == 2

    http.state.update({"status": "ACTIVE", "provisionable": False})
    health.update({"status": "BOUND_ONLINE", "bound": True, "online": True})
    transport = FakeTransport()
    third = watcher.snapshot(Path("/dev/serial/by-id"), watcher.STAGED_HEALTH_ORIGIN, SERVER, {MAC},
                             staged_provisioner=provisioner)
    assert third[0]["provisioning_phase"] == "active"
    assert transport.closed
    assert len([r for r in http.requests if r["path"].startswith(
        "/api/kiosk-provisioner/usb/complete")]) == 1
    state.close()

