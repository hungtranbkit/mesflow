import hashlib

from mesflow.web import execution

from mesflow.services.kiosk_provisioner import validate_service_token, provisioner_uuid_allowed


def test_service_token_fails_closed_without_server_hash():
    assert not validate_service_token("secret", "")


def test_service_token_uses_sha256_and_constant_time_equality():
    token = "only-for-this-test"
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert validate_service_token(token, digest)
    assert not validate_service_token(token + "x", digest)
    assert not validate_service_token("", digest)
    assert not validate_service_token(token, "not-a-sha256")


def test_service_principal_requires_explicit_device_uuid_allowlist():
    target = "fc0c33a9-2f76-424f-a256-217699b57712"
    other = "00000000-0000-4000-8000-000000000001"
    assert not provisioner_uuid_allowed(target, "")
    assert provisioner_uuid_allowed(target, target)
    assert provisioner_uuid_allowed(target, f"{other}, {target.upper()}")
    assert not provisioner_uuid_allowed(other, target)


def test_service_api_requires_dedicated_token_and_exact_allowlist(monkeypatch):
    from mesflow.web.app import create_app

    token = "only-for-this-test"
    target = "fc0c33a9-2f76-424f-a256-217699b57712"
    other = "00000000-0000-4000-8000-000000000001"
    monkeypatch.setenv("MESFLOW_KIOSK_PROVISIONER_TOKEN_SHA256", hashlib.sha256(token.encode()).hexdigest())
    monkeypatch.setenv("MESFLOW_KIOSK_PROVISIONER_DEVICE_UUIDS", target)
    monkeypatch.setattr(execution.instance_identity, "current", lambda: {"state": "VERIFIED"})
    monkeypatch.setattr(execution.KioskRepository, "usb_provision_status",
                        lambda self, device_uuid: {"status": "PENDING", "device_uuid": device_uuid})

    client = create_app().test_client()
    path = "/api/kiosk-provisioner/usb/status?device_uuid="
    missing = client.get(path + target)
    assert missing.status_code == 401
    assert missing.json["code"] == "PROVISIONER_AUTH_REQUIRED"

    denied = client.get(path + other, headers={"X-MESFlow-Provisioner": token})
    assert denied.status_code == 403
    assert denied.json["code"] == "DEVICE_NOT_ALLOWLISTED"

    allowed = client.get(path + target, headers={"X-MESFlow-Provisioner": token})
    assert allowed.status_code == 200
    assert allowed.json["device_uuid"] == target
