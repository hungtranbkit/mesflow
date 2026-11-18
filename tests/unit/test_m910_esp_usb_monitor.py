import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

M = Path(__file__).resolve().parents[2] / "tools" / "m910_esp_usb_monitor.py"
spec = importlib.util.spec_from_file_location("m910_esp_usb_monitor", M)
monitor = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = monitor
spec.loader.exec_module(monitor)


class TestM910Monitor(unittest.TestCase):
    def test_mac_id_unique(self):
        m = monitor.AttachedEsp(Path("/dev/serial/by-id/k"), Path("/dev/ttyACM0"), "84:C7:BB:79:39:6C")
        self.assertEqual(m.proposed_id, "ESP32-KIOSK-396C")

    def test_deny_untrusted_usb(self):
        with patch.object(monitor, "discover_usb", return_value=[
            monitor.AttachedEsp(Path("b"), Path("t"), "AA:BB:CC:DD:EE:FF")
        ]):
            result = monitor.snapshot(Path("/dev/null"), "http://x:123", "https://mesflow.net:443",
                                      {"84:C7:BB:79:39:6C"})
        self.assertEqual(result[0]["status"], "UNTRUSTED_USB_DENY")

    def test_mac_mismatch_fail_closed(self):
        attached = monitor.AttachedEsp(Path("b"), Path("t"), "84:C7:BB:79:39:6C")
        payload = {"network": {"mac": "AA:BB:CC:DD:EE:FF", "server_url": "https://mesflow.net:443"},
                   "mes": {"bound": False, "offline_queue": 0}}
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return json.dumps(payload).encode()
        with patch.object(monitor, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "MAC_MISMATCH"):
                monitor.check_health(attached)

    def test_pending_queue_preserved(self):
        attached = monitor.AttachedEsp(Path("b"), Path("t"), "84:C7:BB:79:39:6C")
        payload = {"network": {"mac": attached.mac, "server_url": "https://mesflow.net:443"},
                   "mes": {"bound": False, "offline_queue": 1, "pending_transaction": True}}
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return json.dumps(payload).encode()
        with patch.object(monitor, "urlopen", return_value=Response()):
            self.assertEqual(monitor.check_health(attached)["status"], "BUSY_PRESERVE_STATE")

    def test_never_calls_mutation_method(self):
        source = M.read_text()
        self.assertNotIn("urlopen(req", source)
        self.assertNotIn("write-flash", source)
        self.assertNotIn("delete", source)

    def test_known_url_missing(self):
        attached = monitor.AttachedEsp(Path("b"), Path("t"), "84:C7:BB:79:39:6C")
        payload = {"network": {"mac": attached.mac, "server_url": ""},
                   "mes": {"bound": False, "offline_queue": 0}}
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return json.dumps(payload).encode()
        with patch.object(monitor, "urlopen", return_value=Response()):
            self.assertEqual(monitor.check_health(attached)["status"], "SERVER_CONFIG_REQUIRED")


if __name__ == "__main__":
    unittest.main()
