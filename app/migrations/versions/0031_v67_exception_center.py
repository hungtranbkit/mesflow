"""V67 Exception Center: durable incidents and immutable history."""
from alembic import op

revision="0031_v67_exception_center"
down_revision="0030_v66_audit_foundation"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("""CREATE TABLE exception_records(
      id BIGSERIAL PRIMARY KEY,
      exception_type TEXT NOT NULL,
      severity TEXT NOT NULL CHECK(severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
      status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACKNOWLEDGED','RESOLVED','AUTO_IGNORED','MANUAL_IGNORED')),
      entity_type TEXT NOT NULL, entity_id BIGINT NOT NULL,
      employee_id BIGINT REFERENCES employees(id) ON DELETE SET NULL,
      production_order_id BIGINT REFERENCES production_orders(id) ON DELETE SET NULL,
      part_id BIGINT REFERENCES parts(id) ON DELETE SET NULL,
      operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
      session_id BIGINT REFERENCES work_sessions(id) ON DELETE SET NULL,
      title TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', recommended_action TEXT NOT NULL DEFAULT '',
      fingerprint TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      condition_active BOOLEAN NOT NULL DEFAULT TRUE,
      occurrence_no INTEGER NOT NULL DEFAULT 1 CHECK(occurrence_no>0),
      row_version INTEGER NOT NULL DEFAULT 1 CHECK(row_version>0),
      detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      acknowledged_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ, ignored_at TIMESTAMPTZ,
      acknowledged_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
      resolved_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
      auto_ignore_reason TEXT, auto_ignored_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("CREATE UNIQUE INDEX uq_exception_active_fingerprint ON exception_records(fingerprint) WHERE status IN ('OPEN','ACKNOWLEDGED')")
    op.execute("CREATE INDEX idx_exception_status_severity_time ON exception_records(status,severity,detected_at DESC)")
    op.execute("CREATE INDEX idx_exception_session ON exception_records(session_id) WHERE session_id IS NOT NULL")
    op.execute("CREATE INDEX idx_exception_entity ON exception_records(entity_type,entity_id)")
    op.execute("CREATE INDEX idx_exception_fingerprint ON exception_records(fingerprint)")
    op.execute("""CREATE TABLE exception_history(
      id BIGSERIAL PRIMARY KEY,
      exception_id BIGINT NOT NULL REFERENCES exception_records(id) ON DELETE CASCADE,
      action TEXT NOT NULL, previous_status TEXT, new_status TEXT NOT NULL,
      actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
      actor_username TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, correlation_id TEXT NOT NULL DEFAULT '',
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("CREATE INDEX idx_exception_history_time ON exception_history(exception_id,created_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_exception_history_correlation ON exception_history(correlation_id) WHERE correlation_id<>''")
    op.execute("UPDATE system_meta SET value='67.0.0.1',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.execute("DROP TABLE IF EXISTS exception_history")
    op.execute("DROP TABLE IF EXISTS exception_records")
