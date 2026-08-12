from alembic import op
import sqlalchemy as sa

revision='0020_log_retention'
down_revision='0019_operation_input_consumption_ledger'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('error_traces',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('trace_id',sa.Text(),nullable=False),
        sa.Column('action_log_id',sa.BigInteger(),sa.ForeignKey('action_logs.id',ondelete='SET NULL')),
        sa.Column('severity',sa.Text(),nullable=False,server_default='ERROR'),
        sa.Column('error_type',sa.Text(),nullable=False,server_default=''),
        sa.Column('error_message',sa.Text(),nullable=False,server_default=''),
        sa.Column('traceback_text',sa.Text(),nullable=False,server_default=''),
        sa.Column('path',sa.Text(),nullable=False,server_default=''),
        sa.Column('resolved',sa.Boolean(),nullable=False,server_default=sa.text('false')),
        sa.Column('resolved_by_user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('resolved_note',sa.Text(),nullable=False,server_default=''),
        sa.Column('resolved_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_index('idx_error_traces_created','error_traces',['created_at'])
    op.create_index('idx_error_traces_resolved','error_traces',['resolved','created_at'])
    op.create_index('idx_error_traces_trace_id','error_traces',['trace_id'])
    op.create_table('log_retention_runs',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('dry_run',sa.Boolean(),nullable=False,server_default=sa.text('false')),
        sa.Column('action_deleted',sa.BigInteger(),nullable=False,server_default='0'),
        sa.Column('error_deleted',sa.BigInteger(),nullable=False,server_default='0'),
        sa.Column('details_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('finished_at',sa.DateTime(timezone=True)))
    op.execute("UPDATE system_meta SET value='65.8.38',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_table('log_retention_runs')
    op.drop_table('error_traces')
