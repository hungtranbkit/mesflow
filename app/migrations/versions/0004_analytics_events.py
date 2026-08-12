from alembic import op
import sqlalchemy as sa

revision='0004_analytics_events'
down_revision='0003_execution'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('kiosk_events',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('event_uuid',sa.Text(),nullable=False,unique=True),
        sa.Column('device_uuid',sa.Text(),nullable=False),
        sa.Column('station_id',sa.BigInteger(),sa.ForeignKey('stations.id',ondelete='SET NULL')),
        sa.Column('event_type',sa.Text(),nullable=False),
        sa.Column('severity',sa.Text(),nullable=False,server_default='INFO'),
        sa.Column('status',sa.Text(),nullable=False,server_default='OPEN'),
        sa.Column('message',sa.Text(),nullable=False,server_default=''),
        sa.Column('payload_json',sa.JSON(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column('session_id',sa.BigInteger(),sa.ForeignKey('work_sessions.id',ondelete='SET NULL')),
        sa.Column('operation_id',sa.BigInteger(),sa.ForeignKey('operations.id',ondelete='SET NULL')),
        sa.Column('employee_id',sa.BigInteger(),sa.ForeignKey('employees.id',ondelete='SET NULL')),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('received_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('resolved_at',sa.DateTime(timezone=True)),
        sa.Column('resolved_by',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('resolution_note',sa.Text(),nullable=False,server_default=''))
    op.create_index('idx_kiosk_events_device_time','kiosk_events',['device_uuid','occurred_at'])
    op.create_index('idx_kiosk_events_status_severity','kiosk_events',['status','severity','occurred_at'])
    op.create_index('idx_kiosk_events_station_time','kiosk_events',['station_id','occurred_at'])

    op.create_table('notifications',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('source_type',sa.Text(),nullable=False,server_default='SYSTEM'),
        sa.Column('source_id',sa.Text(),nullable=False,server_default=''),
        sa.Column('severity',sa.Text(),nullable=False,server_default='INFO'),
        sa.Column('title',sa.Text(),nullable=False),
        sa.Column('message',sa.Text(),nullable=False,server_default=''),
        sa.Column('status',sa.Text(),nullable=False,server_default='UNREAD'),
        sa.Column('target_role',sa.Text(),nullable=False,server_default=''),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('read_at',sa.DateTime(timezone=True)),
        sa.Column('read_by',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.UniqueConstraint('source_type','source_id',name='uq_notifications_source'))
    op.create_index('idx_notifications_status_created','notifications',['status','created_at'])
    op.create_index('idx_notifications_role_status','notifications',['target_role','status'])

    op.create_table('kpi_snapshots',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('snapshot_date',sa.Date(),nullable=False),
        sa.Column('scope_type',sa.Text(),nullable=False),
        sa.Column('scope_id',sa.Text(),nullable=False),
        sa.Column('metrics_json',sa.JSON(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('snapshot_date','scope_type','scope_id',name='uq_kpi_snapshot_scope'))
    op.create_index('idx_kpi_snapshots_scope_date','kpi_snapshots',['scope_type','scope_id','snapshot_date'])

    op.create_index('idx_audit_logs_entity','audit_logs',['entity_type','entity_id','created_at'])
    op.execute("UPDATE system_meta SET value='65.3.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_index('idx_audit_logs_entity',table_name='audit_logs')
    op.drop_table('kpi_snapshots')
    op.drop_table('notifications')
    op.drop_table('kiosk_events')
