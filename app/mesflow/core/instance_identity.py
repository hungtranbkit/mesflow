"""MESFlow instance identity used to scope ESP OTA ownership.

instance_id  : system_meta.mesflow_instance_id (migration 0055), stable across
               domain changes / VPS moves because it lives in the database.
binding      : system_meta.mesflow_instance_binding = sha256(id + install
               secret). The install secret is MESFLOW_INSTANCE_SECRET, falling
               back to MESFLOW_INTERNAL_API_TOKEN (already unique per install
               and shared only with this install's Deploy Agent).

States
  VERIFIED          id present and bound to this install's secret
  UNVERIFIED_CLONE  DB carries a binding made with a different secret: a
                    restored/cloned DB on another install. OTA fails closed.
  UNVERIFIED_NO_SECRET  no install secret configured.
  MISSING           migration 0055 not applied.

Owner actions (CLI, never automatic):
  python -m mesflow.core.instance_identity show
  python -m mesflow.core.instance_identity adopt        # same system, moved VPS / rotated secret
  python -m mesflow.core.instance_identity new-install  # clone becomes a NEW instance (new id)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import uuid
from urllib.parse import urlparse

from mesflow.db.connection import execute, fetch_one

ID_KEY = "mesflow_instance_id"
BINDING_KEY = "mesflow_instance_binding"


def _secret() -> str:
    return str(os.environ.get("MESFLOW_INSTANCE_SECRET") or os.environ.get("MESFLOW_INTERNAL_API_TOKEN") or "").strip()


def _binding(instance_id: str, secret: str) -> str:
    return hashlib.sha256(f"mesflow-instance:v1:{instance_id}:{secret}".encode()).hexdigest()


def _meta(key: str) -> str:
    row = fetch_one("SELECT value FROM system_meta WHERE key=%s", (key,))
    return str(row["value"]) if row else ""


def ota_agent_url() -> str:
    """Instance-configured Deploy Agent URL advertised to this instance's kiosks.
    HTTPS only; no default -- a new install never silently points at another
    owner's Agent."""
    value = str(os.environ.get("MESFLOW_OTA_AGENT_URL") or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    return value if len(value) < 190 else ""


def evaluate(instance_id: str, stored_binding: str, secret: str) -> str:
    if not instance_id: return "MISSING"
    if not secret: return "UNVERIFIED_NO_SECRET"
    if not stored_binding: return "UNBOUND"
    return "VERIFIED" if hmac.compare_digest(stored_binding, _binding(instance_id, secret)) else "UNVERIFIED_CLONE"


def current() -> dict:
    instance_id, secret = _meta(ID_KEY), _secret()
    state = evaluate(instance_id, _meta(BINDING_KEY), secret)
    if state == "UNBOUND":
        # First verification on this install: record the binding exactly once.
        execute("INSERT INTO system_meta(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING", (BINDING_KEY, _binding(instance_id, secret)))
        state = evaluate(instance_id, _meta(BINDING_KEY), secret)
    return {"instance_id": instance_id, "state": state,
            "display_name": str(os.environ.get("MESFLOW_INSTANCE_NAME") or "")[:120],
            "public_url": str(os.environ.get("MESFLOW_PUBLIC_URL") or "")[:200],
            "ota_agent_url": ota_agent_url()}


def adopt() -> dict:
    instance_id, secret = _meta(ID_KEY), _secret()
    if not instance_id or not secret: raise SystemExit("instance id or install secret missing")
    execute("INSERT INTO system_meta(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
            (BINDING_KEY, _binding(instance_id, secret)))
    return current()


def new_install() -> dict:
    secret = _secret()
    if not secret: raise SystemExit("install secret missing")
    new_id = str(uuid.uuid4())
    execute("INSERT INTO system_meta(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP", (ID_KEY, new_id))
    execute("INSERT INTO system_meta(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
            (BINDING_KEY, _binding(new_id, secret)))
    return current()


if __name__ == "__main__":  # pragma: no cover - operator CLI
    action = (sys.argv[1:] or ["show"])[0]
    result = {"show": current, "adopt": adopt, "new-install": new_install}.get(action)
    if not result: raise SystemExit("usage: show|adopt|new-install")
    out = result()
    print({k: out[k] for k in ("instance_id", "state", "ota_agent_url")})
