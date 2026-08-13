from mesflow.core.ota_readiness import evaluate_readiness


def _item(**overrides):
    value = {
        "online": True,
        "ui_state": "READY",
        "offline_queue_count": 0,
        "health_state": "OK",
        "active_session": False,
    }
    value.update(overrides)
    return value


def test_ready_shared_kiosk_with_open_session_is_ota_ready():
    result = evaluate_readiness(_item(active_session=True))
    assert result["active_session"] is True
    assert result["idle"] is True
    assert result["ota_ready"] is True
    assert result["reason"] == "READY"


def test_busy_ui_is_blocked_even_when_session_diagnostic_is_false():
    for ui_state in ("INPUT_GOOD", "INPUT_DEFECT", "CONFIRM_QTY"):
        result = evaluate_readiness(_item(ui_state=ui_state))
        assert result["ota_ready"] is False
        assert result["reason"] == "DEVICE_BUSY"


def test_queue_offline_and_unhealthy_are_blocked():
    assert evaluate_readiness(_item(offline_queue_count=1))["reason"] == "WAITING_SYNC"
    assert evaluate_readiness(_item(online=False))["reason"] == "OFFLINE"
    for health_state in ("ERROR", "DEGRADED"):
        result = evaluate_readiness(_item(health_state=health_state))
        assert result["ota_ready"] is False
        assert result["reason"] == "DEVICE_NOT_HEALTHY"
