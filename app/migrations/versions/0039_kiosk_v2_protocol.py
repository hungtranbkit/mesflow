"""Kiosk v2 protocol: envelope idempotency, per-device projection, UI bundles.

Adds the real, DB-backed persistence the new /api/kiosk/v2/* adapter
(mesflow.web.kiosk_v2) needs, on top of the EXISTING authoritative business
services (WorkSessionRepository.start/finish, KioskRepositoryLookup) --
this migration does not touch employees/operations/production_orders/
work_sessions at all, it only adds v2-protocol-specific bookkeeping:

- kiosk_v2_events: full-envelope idempotency (device_id, event_id) ->
  cached response, independent of kiosk_idempotency (which is keyed by
  request_id and only covers the START/FINISH business mutations
  themselves -- SCAN steps that don't call start/finish need their own
  replay behavior too).
- kiosk_v2_projection: one row per device, the kiosk v2 business-state
  machine (WAIT_EMPLOYEE/WAIT_OPERATION/SESSION_ACTIVE/QUANTITY_INPUT/
  DEVICE_DISABLED/MAINTENANCE) with a monotonic state_version and the
  view-model fields the firmware's StateProjection expects, so a device
  can be resynced (GET /state) without replaying every event.
- kiosk_v2_ui_bundles / kiosk_v2_ui_desired: the backend-managed,
  download-on-change UI bundle registry (Phase 4) -- content_json holds
  the same TEXT/RECT/LINE component JSON the firmware's ui_bundle.cpp
  parses; kiosk_v2_ui_desired is a deliberately single-row table (mirrors
  server_generation's own singleton pattern) since there is currently one
  global desired version, not a per-device rollout.
"""
from alembic import op

revision = '0039_kiosk_v2_protocol'
down_revision = '0038_v73_kiosk_dr_reconciliation'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE kiosk_v2_events(
        device_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        device_seq BIGINT NOT NULL DEFAULT 0,
        response_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (device_id, event_id))""")

    op.execute("""CREATE TABLE kiosk_v2_projection(
        device_id TEXT PRIMARY KEY,
        state_name TEXT NOT NULL DEFAULT 'WAIT_EMPLOYEE',
        state_version BIGINT NOT NULL DEFAULT 1,
        workflow_version BIGINT NOT NULL DEFAULT 1,
        employee_id BIGINT,
        employee_name TEXT NOT NULL DEFAULT '',
        operation_id BIGINT,
        operation_code TEXT NOT NULL DEFAULT '',
        operation_name TEXT NOT NULL DEFAULT '',
        work_session_id BIGINT,
        started_at TIMESTAMPTZ,
        target_qty INTEGER NOT NULL DEFAULT 0,
        produced_qty INTEGER NOT NULL DEFAULT 0,
        disabled BOOLEAN NOT NULL DEFAULT FALSE,
        maintenance BOOLEAN NOT NULL DEFAULT FALSE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    op.execute("""CREATE TABLE kiosk_v2_ui_bundles(
        version INTEGER PRIMARY KEY,
        schema_version INTEGER NOT NULL DEFAULT 1,
        sha256 TEXT NOT NULL,
        content_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    op.execute("""CREATE TABLE kiosk_v2_ui_desired(
        id SMALLINT PRIMARY KEY,
        desired_version INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT ck_kiosk_v2_ui_desired_singleton CHECK (id = 1))""")
    op.execute("INSERT INTO kiosk_v2_ui_desired(id, desired_version) VALUES (1, 0)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS kiosk_v2_ui_desired")
    op.execute("DROP TABLE IF EXISTS kiosk_v2_ui_bundles")
    op.execute("DROP TABLE IF EXISTS kiosk_v2_projection")
    op.execute("DROP TABLE IF EXISTS kiosk_v2_events")
