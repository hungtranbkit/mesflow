"""V68 Production Trace: persistent business events and output movements."""
from alembic import op
revision='0032_v68_production_trace';down_revision='0031_v67_exception_center';branch_labels=None;depends_on=None
def upgrade():
    op.execute("""CREATE TABLE production_trace_events(
      id BIGSERIAL PRIMARY KEY,event_type TEXT NOT NULL,category TEXT NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
      actor_name TEXT NOT NULL DEFAULT '',production_order_id BIGINT REFERENCES production_orders(id) ON DELETE SET NULL,
      part_id BIGINT REFERENCES parts(id) ON DELETE SET NULL,operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
      session_id BIGINT REFERENCES work_sessions(id) ON DELETE SET NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
      quantity_delta INTEGER,metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,correlation_id TEXT NOT NULL DEFAULT '',
      session_trace_id TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT 'NATIVE',created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK(category IN ('PO','OPERATION','SESSION','QUANTITY','DEFECT','REWORK','EXCEPTION','CHANGE','SYSTEM'))
    )""")
    op.execute("CREATE INDEX idx_trace_po_time ON production_trace_events(production_order_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_trace_operation_time ON production_trace_events(operation_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_trace_session_time ON production_trace_events(session_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_trace_correlation ON production_trace_events(correlation_id) WHERE correlation_id<>''")
    op.execute("CREATE INDEX idx_trace_session_trace ON production_trace_events(session_trace_id) WHERE session_trace_id<>''")
    op.execute("""CREATE TABLE quantity_movements(
      id BIGSERIAL PRIMARY KEY,movement_type TEXT NOT NULL CHECK(movement_type IN ('GOOD','DEFECT','REPAIRABLE','REWORK_RECOVERED','SCRAP')),
      delta INTEGER NOT NULL,previous_value INTEGER NOT NULL,new_value INTEGER NOT NULL,
      production_order_id BIGINT REFERENCES production_orders(id) ON DELETE SET NULL,operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
      session_id BIGINT REFERENCES work_sessions(id) ON DELETE SET NULL,actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
      actor_name TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',correlation_id TEXT NOT NULL DEFAULT '',
      session_trace_id TEXT NOT NULL DEFAULT '',metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("CREATE INDEX idx_quantity_po_time ON quantity_movements(production_order_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_quantity_operation_time ON quantity_movements(operation_id,occurred_at DESC,id DESC)")
    op.execute("CREATE INDEX idx_quantity_session_time ON quantity_movements(session_id,occurred_at DESC,id DESC)")
    op.execute("UPDATE system_meta SET value='68.0.0.1',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade():
    op.execute('DROP TABLE IF EXISTS quantity_movements');op.execute('DROP TABLE IF EXISTS production_trace_events')
