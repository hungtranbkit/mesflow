from alembic import op
import sqlalchemy as sa
revision='0016_action_error_logs'
down_revision='0015'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('action_logs',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('trace_id',sa.Text(),nullable=False,unique=True),
        sa.Column('parent_trace_id',sa.Text()),
        sa.Column('actor_user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('actor_username',sa.Text(),nullable=False,server_default=''),
        sa.Column('actor_role',sa.Text(),nullable=False,server_default=''),
        sa.Column('source_type',sa.Text(),nullable=False,server_default='WEB'),
        sa.Column('device_uuid',sa.Text(),nullable=False,server_default=''),
        sa.Column('station_code',sa.Text(),nullable=False,server_default=''),
        sa.Column('method',sa.Text(),nullable=False),sa.Column('path',sa.Text(),nullable=False),
        sa.Column('endpoint',sa.Text(),nullable=False,server_default=''),sa.Column('action_name',sa.Text(),nullable=False,server_default=''),
        sa.Column('http_status',sa.Integer()),sa.Column('duration_ms',sa.Integer()),
        sa.Column('outcome',sa.Text(),nullable=False,server_default='SUCCESS'),
        sa.Column('error_type',sa.Text(),nullable=False,server_default=''),sa.Column('error_message',sa.Text(),nullable=False,server_default=''),
        sa.Column('request_json',sa.Text(),nullable=False,server_default='{}'),sa.Column('response_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('context_json',sa.Text(),nullable=False,server_default='{}'),sa.Column('traceback_text',sa.Text(),nullable=False,server_default=''),
        sa.Column('client_ip',sa.Text(),nullable=False,server_default=''),sa.Column('user_agent',sa.Text(),nullable=False,server_default=''),
        sa.Column('resolved',sa.Boolean(),nullable=False,server_default=sa.text('false')),
        sa.Column('resolved_by_user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('resolved_note',sa.Text(),nullable=False,server_default=''),sa.Column('resolved_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_index('idx_action_logs_created','action_logs',['created_at'])
    op.create_index('idx_action_logs_outcome','action_logs',['outcome','resolved','created_at'])
    op.create_index('idx_action_logs_actor','action_logs',['actor_username','created_at'])
    op.create_index('idx_action_logs_device','action_logs',['device_uuid','station_code','created_at'])
    op.create_index('idx_action_logs_path','action_logs',['path','created_at'])
    op.execute("UPDATE system_meta SET value='65.8.18',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade(): op.drop_table('action_logs')
