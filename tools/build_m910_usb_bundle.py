#!/usr/bin/env python3
"""Build a deterministic, credential-free M910 watcher+adapter source bundle."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = "mesflow-m910-kiosk-provisioner"
VERSION = "0.1.0"
PREFIX = f"{NAME}-{VERSION}"
FILES = {
    "tools/m910_esp_usb_monitor.py": "bin/m910_esp_usb_monitor.py",
    "tools/m910_usb_provisioner.py": "bin/m910_usb_provisioner.py",
    "tools/m910_usb_bundle_manifest.json": "manifest.json",
    "tools/m910_usb_bundle_requirements.txt": "requirements.txt",
    "tools/m910_usb_bundle_README.md": "README.md",
    "tools/m910_usb_provisioner.example.toml": "etc/m910_usb_provisioner.example.toml",
}


def _member(name: str, data: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{PREFIX}/{name}")
    info.size = len(data)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    return info


def build_bundle(output: str | Path) -> str:
    payloads = {dest: (ROOT / source).read_bytes() for source, dest in FILES.items()}
    manifest = json.loads(payloads["manifest.json"])
    if manifest.get("version") != VERSION or manifest.get("runtime_default") != "READ_ONLY":
        raise ValueError("bundle_manifest_version_or_default_mode_mismatch")
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                   for name, data in sorted(payloads.items())).encode()
    payloads["SHA256SUMS"] = sums
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, data in sorted(payloads.items()):
                archive.addfile(_member(name, data), io.BytesIO(data))
    artifact = compressed.getvalue()
    target.write_bytes(artifact)
    return hashlib.sha256(artifact).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("dist") / f"{PREFIX}.tar.gz")
    args = parser.parse_args(argv)
    digest = build_bundle(args.output)
    print(f"artifact={args.output}")
    print(f"version={VERSION}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
