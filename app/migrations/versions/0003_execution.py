from alembic import op
import sqlalchemy as sa

revision='0003_execution'
down_revision='0002_master_data'
branch_labels=None
depends_on=None

def timestamps():
    return (
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
    )

def upgrade():
    op.create_table('kiosk_identities',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('device_uuid',sa.Text(),nullable=False,unique=True),
        sa.Column('device_name',sa.Text(),nullable=False,server_default=''),
        sa.Column('station_id',sa.BigInteger(),sa.ForeignKey('stations.id',ondelete='SET NULL')),
        sa.Column('status',sa.Text(),nullable=False,server_default='PENDING'),
        sa.Column('token_hash',sa.Text(),nullable=False,server_default=''),
        sa.Column('firmware_version',sa.Text(),nullable=False,server_default=''),
        sa.Column('last_ip',sa.Text(),nullable=False,server_default=''),
        sa.Column('last_seen_at',sa.DateTime(timezone=True)),*timestamps())
    op.create_index('idx_kiosk_identity_status','kiosk_identities',['status','station_id'])
    op.create_table('kiosk_status',
        sa.Column('device_uuid',sa.Text(),primary_key=True),
        sa.Column('station_id',sa.BigInteger(),sa.ForeignKey('stations.id',ondelete='SET NULL')),
        sa.Column('ui_state',sa.Text(),nullable=False,server_default='UNKNOWN'),
        sa.Column('health_state',sa.Text(),nullable=False,server_default='UNKNOWN'),
        sa.Column('queue_size',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('wifi_rssi',sa.Integer()),sa.Column('free_heap',sa.BigInteger()),
        sa.Column('last_error',sa.Text(),nullable=False,server_default=''),
        sa.Column('last_heartbeat_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_table('work_sessions',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('employee_id',sa.BigInteger(),sa.ForeignKey('employees.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('operation_id',sa.BigInteger(),sa.ForeignKey('operations.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('station_id',sa.BigInteger(),sa.ForeignKey('stations.id',ondelete='SET NULL')),
        sa.Column('device_uuid',sa.Text(),nullable=False,server_default=''),
        sa.Column('status',sa.Text(),nullable=False,server_default='OPEN'),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('ended_at',sa.DateTime(timezone=True)),
        sa.Column('good_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('defect_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('note',sa.Text(),nullable=False,server_default=''),
        sa.Column('start_request_id',sa.Text(),nullable=False,unique=True),
        sa.Column('finish_request_id',sa.Text(),unique=True),*timestamps())
    op.create_index('idx_work_sessions_operation','work_sessions',['operation_id','started_at'])
    op.create_index('idx_work_sessions_employee','work_sessions',['employee_id','started_at'])
    op.execute("CREATE UNIQUE INDEX uq_open_session_per_employee ON work_sessions(employee_id) WHERE status='OPEN'")
    op.create_table('kiosk_idempotency',
        sa.Column('request_id',sa.Text(),primary_key=True),
        sa.Column('action',sa.Text(),nullable=False),
        sa.Column('response_json',sa.JSON(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_table('qc_inspections',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('session_id',sa.BigInteger(),sa.ForeignKey('work_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('operation_id',sa.BigInteger(),sa.ForeignKey('operations.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('inspector_user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('status',sa.Text(),nullable=False,server_default='OPEN'),
        sa.Column('good_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('defect_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('defect_reason',sa.Text(),nullable=False,server_default=''),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at',sa.DateTime(timezone=True)),*timestamps())
    op.create_index('idx_qc_status_operation','qc_inspections',['status','operation_id'])
    op.create_table('operation_adjustments',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('session_id',sa.BigInteger(),sa.ForeignKey('work_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('operation_id',sa.BigInteger(),sa.ForeignKey('operations.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('old_good_qty',sa.Integer(),nullable=False),sa.Column('new_good_qty',sa.Integer(),nullable=False),
        sa.Column('old_defect_qty',sa.Integer(),nullable=False),sa.Column('new_defect_qty',sa.Integer(),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('adjusted_by',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_table('penalty_tickets',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('employee_id',sa.BigInteger(),sa.ForeignKey('employees.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('operation_id',sa.BigInteger(),sa.ForeignKey('operations.id',ondelete='SET NULL')),
        sa.Column('session_id',sa.BigInteger(),sa.ForeignKey('work_sessions.id',ondelete='SET NULL')),
        sa.Column('points',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('reason',sa.Text(),nullable=False),sa.Column('status',sa.Text(),nullable=False,server_default='OPEN'),
        sa.Column('issued_by',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('resolved_at',sa.DateTime(timezone=True)),*timestamps())
    op.execute("UPDATE system_meta SET value='65.2.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    for name in ('penalty_tickets','operation_adjustments','qc_inspections','kiosk_idempotency','work_sessions','kiosk_status','kiosk_identities'):
        op.drop_table(name)
