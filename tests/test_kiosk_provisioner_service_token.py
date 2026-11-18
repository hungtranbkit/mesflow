import hashlib

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
