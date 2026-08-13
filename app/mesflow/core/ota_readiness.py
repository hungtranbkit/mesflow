"""Pure instantaneous safety policy shared by the internal OTA contract."""


def evaluate_readiness(item):
    """Evaluate current kiosk safety, never historical production sessions."""
    online = bool(item.get("online"))
    ui_state = str(item.get("ui_state") or "").upper()
    queue_count = int(item.get("offline_queue_count") or 0)
    health_state = str(item.get("health_state") or "").upper()
    item["idle"] = bool(online and ui_state == "READY")
    item["health_ok"] = health_state in {"OK", "HEALTHY", "READY"}
    item["ota_ready"] = bool(item["idle"] and queue_count == 0 and item["health_ok"])
    if not online:
        item["reason"] = "OFFLINE"
    elif ui_state != "READY":
        item["reason"] = "DEVICE_BUSY"
    elif queue_count > 0:
        item["reason"] = "WAITING_SYNC"
    elif not item["health_ok"]:
        item["reason"] = "DEVICE_NOT_HEALTHY"
    else:
        item["reason"] = "READY"
    return item
