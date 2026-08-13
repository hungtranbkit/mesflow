from __future__ import annotations

import hmac
import os
from flask import Blueprint, jsonify, request

from mesflow.db.connection import fetch_all, fetch_one
from mesflow.db.repositories.execution import KioskRepository
from mesflow.core.ota_readiness import evaluate_readiness

bp = Blueprint("internal_ota", __name__)


def _internal_allowed():
    expected = str(os.environ.get("MESFLOW_INTERNAL_API_TOKEN") or "").strip()
    supplied = str(request.headers.get("X-MESFlow-Internal-Token") or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _device_allowed(device_uuid):
    if _internal_allowed(): return True
    token = str(request.headers.get("X-Kiosk-Token") or "").strip()
    if not token: return False
    try: return KioskRepository().verify_token_any(token).get("device_uuid") == device_uuid
    except Exception: return False


def _readiness(device_uuid):
    row = fetch_one("""SELECT ki.device_uuid kiosk_id,ki.device_name kiosk_name,ki.hardware_model,
      ki.firmware_version,ki.firmware_build,ki.ota_capable,ki.last_seen_at,
      ks.ui_state,ks.health_state,COALESCE(ks.queue_size,0) offline_queue_count,ks.last_heartbeat_at,
      CASE WHEN ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes' THEN TRUE ELSE FALSE END online,
      EXISTS(SELECT 1 FROM work_sessions ws WHERE ws.device_uuid=ki.device_uuid AND ws.status='OPEN') active_session
      FROM kiosk_identities ki LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
      WHERE ki.device_uuid=%s AND ki.status='ACTIVE'""", (device_uuid,))
    if not row: return None
    return evaluate_readiness(dict(row))


@bp.get("/api/internal/kiosks")
def kiosks():
    if not _internal_allowed(): return jsonify(ok=False,error="AUTH_REQUIRED"), 401
    rows = fetch_all("""SELECT ki.device_uuid kiosk_id,ki.device_name kiosk_name,ki.hardware_model,
      ki.firmware_version,ki.firmware_build,ki.ota_capable,ki.last_seen_at,
      ks.ui_state,ks.health_state,COALESCE(ks.queue_size,0) offline_queue_count,
      CASE WHEN ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes' THEN TRUE ELSE FALSE END online
      FROM kiosk_identities ki LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
      WHERE ki.status='ACTIVE' ORDER BY ki.device_uuid""")
    return jsonify(ok=True,items=[dict(x) for x in rows])


@bp.get("/api/internal/kiosks/<device_uuid>/ota-readiness")
def readiness(device_uuid):
    if not _device_allowed(device_uuid): return jsonify(ok=False,error="FORBIDDEN"), 403
    item = _readiness(device_uuid)
    return (jsonify(ok=True,**item), 200) if item else (jsonify(ok=False,error="NOT_FOUND"), 404)
