# MESFlow M910 USB kiosk bundle

Bundle version: `0.1.0`. This package contains the existing USB-by-id/LAN
watcher and its single-port enrollment adapter. It does not install or enable a
service. Runtime mode is **read-only** unless the operator supplies a protected
manifest and explicitly passes `--enable-staged-provisioning`.

Build one deterministic source artifact from the repository root:

```sh
python3 tools/build_m910_usb_bundle.py --output dist/mesflow-m910-kiosk-provisioner-0.1.0.tar.gz
sha256sum dist/mesflow-m910-kiosk-provisioner-0.1.0.tar.gz
```

Extract it into a reviewed, isolated staging directory. Install the exact
dependency in the manifest from an approved package source. A read-only
inspection uses `python3 bin/m910_esp_usb_monitor.py --once`. Staged mutation
requires a separate 0600 TOML file, separate 0600 service-token and Wi-Fi
credential files, a verified HTTPS origin/CA, server-side UUID allowlisting,
and this explicit invocation:

```sh
python3 bin/m910_esp_usb_monitor.py --watch --enable-staged-provisioning \
  --provisioner-config /etc/mesflow/kiosk-provisioner/manifest.toml
```

No live credentials/configuration are included. Never enable this against
production based only on this source artifact or offline tests. Staged mode
pins LAN health to `http://192.168.1.254:17892` and refuses redirects. That
health endpoint is unauthenticated HTTP and must run on a physically trusted
private network. The initial USB HELLO is also unsigned; it must report the
manifest's version/build pattern/protocol/model, then the challenge HMAC
authenticates the device before server claim. Wi-Fi config is sent over USB
before that proof because a fresh device needs Wi-Fi to create its PENDING
server identity; physical control of the M910 USB port remains required.
`ACTIVE` is reported only when the server identity is ACTIVE and LAN health
independently reports bound+online. A successful HTTP claim alone remains
`awaiting-active`.
