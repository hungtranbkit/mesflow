"""Narrow authentication helpers for the trusted M910 USB provisioner."""
import hashlib
import hmac
import re
import uuid


def validate_service_token(token: str, configured_sha256: str) -> bool:
    """Match a dedicated provisioner credential to its server-side hash.

    The raw credential is supplied only in the request header and is never
    stored or included in errors/audit metadata. An absent or malformed
    server hash disables the service-principal API.
    """
    digest = str(configured_sha256 or "").strip().lower()
    raw = str(token or "")
    if not raw or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(actual, digest)


def provisioner_uuid_allowed(device_uuid: str, configured_uuids: str) -> bool:
    """Require an explicit per-identity UUID allowlist for service actions."""
    try:
        requested = str(uuid.UUID(str(device_uuid or "").strip()))
        allowed = {str(uuid.UUID(item.strip())) for item in str(configured_uuids or "").split(",") if item.strip()}
    except (ValueError, AttributeError, TypeError):
        return False
    return bool(allowed) and requested in allowed
