from alembic import op
import sqlalchemy as sa
revision='0001_core'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('system_meta',
        sa.Column('key',sa.Text(),primary_key=True),
        sa.Column('value',sa.Text(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_table('users',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('username',sa.Text(),nullable=False,unique=True),
        sa.Column('display_name',sa.Text(),nullable=False),
        sa.Column('password_hash',sa.Text(),nullable=False),
        sa.Column('role',sa.Text(),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),
        sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.text('false')),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_index('idx_users_active_role','users',['active','role'])
    op.create_table('audit_logs',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('actor_username',sa.Text(),nullable=False,server_default=''),
        sa.Column('action',sa.Text(),nullable=False),
        sa.Column('entity_type',sa.Text(),nullable=False,server_default=''),
        sa.Column('entity_id',sa.Text(),nullable=False,server_default=''),
        sa.Column('details_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_index('idx_audit_logs_created','audit_logs',['created_at'])
    op.execute("INSERT INTO system_meta(key,value) VALUES ('schema_version','65.0.0')")
def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('users')
    op.drop_table('system_meta')
