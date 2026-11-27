# Kiosk device names (2026-11-27)

Base: deployed 71.0.0.391 source 8009ca6; worktree base 6b46a26 has the same tree.

## Design

- Reuse kiosk_identities.device_name as the canonical human alias; no migration.
- PATCH /api/kiosk-management/<id>/name permits admin/manager and accepts only device_name. Trim, require nonempty UTF-8 up to 63 bytes, reject control characters.
- Rename changes only the name and updated_at. Repeating the current name is a no-op with no duplicate audit. Audit logs KIOSK_RENAME and the previous/new names.
- Device register, claim, rebind and web heartbeat preserve an existing nonblank canonical name. Hardware heartbeat endpoints return device_name; firmware consumes it separately.
- Classic cards and timeline show alias plus the last eight uppercase hex characters of a valid UUID. The full UUID remains visible. Legacy non-UUID identities get no manufactured ESP identifier. No primary key or list-order numbering changes.
- Names need not be unique: stable ID distinguishes equal labels. Devices can be renamed while pending.

## Verification plan

Use an isolated PostgreSQL test project with current source mounted into the existing 71.0.0.391 runtime. Exercise actual HTTP RBAC, validation, idempotence, unchanged identity/token/station/status, register/rebind/claim preservation and both hardware heartbeat responses. Render real Classic assets with API fixtures at 1920, 1366, 768 and 390 pixels; check rename-only payload, stable labels, timeline, validation and overflow.

No version bump, image build, public data changes or deployment before source review. Root owns final integration, device naming and release.

## Verification result and release preparation

- PostgreSQL/API: 24 passed in 3.03s (20 behavior cases and four existing enrollment contracts).
- Classic browser: five passed in 5.8s with the existing Docker Chromium image. Real assets and existing test auto-login; viewports 1920/1366/768/390px, including pending rename and mobile dialog. Screenshots saved under test-results/browser-artifacts-docker.
- Browser testing caught a focus race with shared modal setup; only the rename dialog now waits for modal focus setup before focusing/selecting its input.
- Root review requested friendly validation text and explicit firmware-support wording; both applied.
- Python/JS syntax, git diff check, ProjectFlow preflight and version synchronization pass.
- Version 71.0.0.392 prepared after source review. No frozen image or public deployment yet; canonical build awaits root authorization of the clean commit.
