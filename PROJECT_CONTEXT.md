# MESFlow project context

## Current source snapshot
- GitHub `main` baseline for this task: `8c595689a5d472cc40d318370b6721f7bedece51` (MESFlow #58 merge).
- Live `mesflow.net` readiness evidence in the 2026-11-28 release checkpoint identifies .396 / `9a128a9cfa27077bcc75ae2b35f2a55191b2858e`, Alembic `0057_kiosk_display_number`; do not migrate or deploy production as part of USB enrollment work.
- Current task branch: `agent/codex/usb-enrollment-mainline`; task worktree `/home/dell/workspace/mesflow/.worktrees/codex-usb-enrollment-mainline`.

## USB enrollment integration
- PR #50 supplies stable instance identity and admin-approved kiosk enrollment at migrations 0055/0056. PR #52 adds trusted M910 USB provisioning but its migration 0057 conflicts with the deployed .396 `0057_kiosk_display_number` revision.
- Preserve migration compatibility by retaining the exact deployed `0057_kiosk_display_number` revision, placing USB schema on a sibling migration, and adding a merge revision that joins both heads. This must be verified against isolated PostgreSQL from both pre-0057 and deployed-0057 states before merge.
- USB service must remain unavailable by default (no service-token hash and no UUID allowlist), use dedicated credentials, HTTPS, UUID/MAC and HMAC challenge binding, one-time bounded challenges, no existing-token overwrite, idle/unbound checks, and redacted logs. Do not run the USB provisioning tool against any production device.

## Current verification and deployment
- No tests or builds have been run on this task branch yet.
- No migration, deployment, or device operation has been performed. No version bump is planned for source-only changes.
- Next: review and port the USB service/API/tool from PR #52; tighten any security gaps found, run unit/strict PostgreSQL and repo gates, then update this snapshot with exact results and PR state.
