"""Instance identity + internal OTA scope contract (no PostgreSQL needed).

system_meta / kiosk rows are replaced by an in-memory double behind the
module-level fetch/execute helpers, so these run as unit tests.
"""
from __future__ import annotations

import pytest

from mesflow.core import instance_identity as ii


class Meta:
    def __init__(self, **rows):
        self.rows = dict(rows)

    def fetch_one(self, sql, params=()):
        key = params[0]
        return {"value": self.rows[key]} if key in self.rows else None

    def execute(self, sql, params=()):
        key, value = params
        if "DO NOTHING" in sql and key in self.rows:
            return 0
        self.rows[key] = value
        return 1


@pytest.fixture()
def meta(monkeypatch):
    m = Meta(mesflow_instance_id="11111111-2222-4333-8444-555555555555")
    monkeypatch.setattr(ii, "fetch_one", m.fetch_one)
    monkeypatch.setattr(ii, "execute", m.execute)
    monkeypatch.setenv("MESFLOW_INTERNAL_API_TOKEN", "install-secret-A")
    monkeypatch.delenv("MESFLOW_INSTANCE_SECRET", raising=False)
    monkeypatch.delenv("MESFLOW_OTA_AGENT_URL", raising=False)
    return m


def test_first_contact_binds_and_is_verified(meta):
    cur = ii.current()
    assert cur["state"] == "VERIFIED" and cur["instance_id"] == meta.rows["mesflow_instance_id"]
    assert "mesflow_instance_binding" in meta.rows
    assert ii.current()["state"] == "VERIFIED"


def test_domain_change_or_vps_move_with_same_install_keeps_instance(meta, monkeypatch):
    first = ii.current()
    monkeypatch.setenv("MESFLOW_PUBLIC_URL", "https://new-domain.example")
    again = ii.current()
    assert again["instance_id"] == first["instance_id"] and again["state"] == "VERIFIED"


def test_cloned_db_on_new_install_is_unverified_until_owner_decides(meta, monkeypatch):
    ii.current()
    monkeypatch.setenv("MESFLOW_INTERNAL_API_TOKEN", "install-secret-B")  # another install, same DB copy
    clone = ii.current()
    assert clone["state"] == "UNVERIFIED_CLONE"
    old_id = clone["instance_id"]
    fresh = ii.new_install()
    assert fresh["state"] == "VERIFIED" and fresh["instance_id"] != old_id


def test_adopt_keeps_identity_for_same_system(meta, monkeypatch):
    ii.current()
    monkeypatch.setenv("MESFLOW_INTERNAL_API_TOKEN", "rotated-secret")
    assert ii.current()["state"] == "UNVERIFIED_CLONE"
    adopted = ii.adopt()
    assert adopted["state"] == "VERIFIED" and adopted["instance_id"] == "11111111-2222-4333-8444-555555555555"


def test_missing_secret_or_id_never_verifies(meta, monkeypatch):
    monkeypatch.delenv("MESFLOW_INTERNAL_API_TOKEN")
    assert ii.current()["state"] == "UNVERIFIED_NO_SECRET"
    assert ii.evaluate("", "x", "y") == "MISSING"


@pytest.mark.parametrize("value,expected", [
    ("", ""),
    ("http://deploy.example/agent", ""),
    ("https://user:pw@deploy.example/agent", ""),
    ("https://deploy.example/agent?x=1", ""),
    ("https://deploy.kimex.example/agent/", "https://deploy.kimex.example/agent"),
])
def test_ota_agent_url_is_https_only_and_has_no_default(meta, monkeypatch, value, expected):
    monkeypatch.setenv("MESFLOW_OTA_AGENT_URL", value)
    assert ii.ota_agent_url() == expected


def test_internal_routes_carry_instance_and_fail_closed(monkeypatch, meta):
    from flask import Flask
    from mesflow.web import internal_ota
    app = Flask(__name__)
    app.register_blueprint(internal_ota.bp)
    monkeypatch.setattr(internal_ota, "fetch_all", lambda sql, params=None: [{"kiosk_id": "K1", "station_code": "LASER-01", "hardware_profile": "p1", "online": True}])
    monkeypatch.setattr(internal_ota, "fetch_one", lambda sql, params=None: {
        "kiosk_id": params[0], "online": True, "ui_state": "READY", "offline_queue_count": 0, "health_state": "OK", "active_session": True})
    monkeypatch.setattr(internal_ota, "_device_allowed", lambda uuid: uuid == "K1")
    c = app.test_client()
    h = {"X-MESFlow-Internal-Token": "install-secret-A"}
    assert c.get("/api/internal/instance").status_code == 401
    inst = c.get("/api/internal/instance", headers=h).get_json()
    assert inst["state"] == "VERIFIED"
    inv = c.get("/api/internal/kiosks", headers=h).get_json()
    assert inv["instance_id"] == inst["instance_id"] and inv["items"][0]["station_code"] == "LASER-01"
    r = c.get("/api/internal/kiosks/K1/ota-readiness", headers={"X-Kiosk-Token": "t"}).get_json()
    assert r["instance_id"] == inst["instance_id"] and r["ota_ready"] is True
    assert c.get("/api/internal/kiosks/K2/ota-readiness", headers={"X-Kiosk-Token": "t"}).status_code == 403
    # a cloned install answers readiness with ota_ready False
    monkeypatch.setenv("MESFLOW_INTERNAL_API_TOKEN", "install-secret-B")
    r = c.get("/api/internal/kiosks/K1/ota-readiness", headers={"X-Kiosk-Token": "t"}).get_json()
    assert r["ota_ready"] is False and r["reason"] == "INSTANCE_UNVERIFIED"
