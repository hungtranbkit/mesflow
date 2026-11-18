import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/build_m910_usb_bundle.py"
spec = importlib.util.spec_from_file_location("build_m910_usb_bundle", SCRIPT)
builder = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)


def test_bundle_is_one_reproducible_artifact_with_source_manifest_and_checksums(tmp_path):
    one = tmp_path / "one.tar.gz"
    two = tmp_path / "two.tar.gz"
    digest_one = builder.build_bundle(one)
    digest_two = builder.build_bundle(two)

    assert digest_one == digest_two == hashlib.sha256(one.read_bytes()).hexdigest()
    assert one.read_bytes() == two.read_bytes()
    with tarfile.open(one, "r:gz") as archive:
        files = {item.name: archive.extractfile(item).read()
                 for item in archive.getmembers() if item.isfile()}
    prefix = "mesflow-m910-kiosk-provisioner-0.1.0/"
    assert prefix + "bin/m910_esp_usb_monitor.py" in files
    assert prefix + "bin/m910_usb_provisioner.py" in files
    manifest = json.loads(files[prefix + "manifest.json"])
    assert manifest["runtime_default"] == "READ_ONLY"
    assert manifest["mutation_opt_in"] == "--enable-staged-provisioning"
    assert manifest["firmware"]["required_version"] == "5.6.6"
    assert manifest["firmware"]["required_build_pattern"]
    assert manifest["firmware"]["protocol"] == "MESFLOW-KIOSK-USB-ENROLLMENT-V1"
    assert manifest["firmware"]["feature_commit"] == "2fcafb2db5cfa3f1d8a277a988ef7489d3c07162"
    assert manifest["firmware"]["hello_authentication"] == "unsigned; physical trust assumption"
    assert manifest["lan_health_endpoint"] == "http://192.168.1.254:17892/api/device/health"
    sums = files[prefix + "SHA256SUMS"].decode()
    assert hashlib.sha256(files[prefix + "bin/m910_usb_provisioner.py"]).hexdigest() in sums
