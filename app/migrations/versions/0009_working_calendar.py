from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_working_calendar'
down_revision = '0008_operation_cycle_time'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.execute("""INSERT INTO app_settings(key,value_json) VALUES(
      'working_calendar',
      '{"timezone":"Asia/Ho_Chi_Minh","work_start":"07:30","lunch_start":"11:30","lunch_end":"13:00","work_end":"17:00","working_weekdays":[0,1,2,3,4,5]}'::jsonb
    )""")
    op.execute("UPDATE system_meta SET value='65.7.3',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_table('app_settings')
