from alembic import op
import sqlalchemy as sa

revision = "0017_work_shifts"
down_revision = "0016_action_error_logs"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "work_shifts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Ho_Chi_Minh"),
        sa.Column("anchor_start", sa.Time(), nullable=False),
        sa.Column("anchor_end", sa.Time(), nullable=False),
        sa.Column("cross_midnight", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("target_minutes", sa.Integer(), nullable=False, server_default="480"),
        sa.Column("working_weekdays", sa.ARRAY(sa.SmallInteger()), nullable=False, server_default=sa.text("ARRAY[0,1,2,3,4,5]::smallint[]")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "work_shift_intervals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shift_id", sa.BigInteger(), sa.ForeignKey("work_shifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interval_type", sa.String(20), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("end_minute > start_minute", name="ck_shift_interval_order"),
        sa.CheckConstraint("interval_type IN ('WORK','BREAK')", name="ck_shift_interval_type"),
    )
    op.create_index("idx_work_shift_intervals_shift", "work_shift_intervals", ["shift_id", "sort_order"])
    op.execute("""
      INSERT INTO work_shifts(code,name,timezone,anchor_start,anchor_end,cross_midnight,target_minutes,working_weekdays,sort_order)
      VALUES
        ('DAY','Ca ngày','Asia/Ho_Chi_Minh','08:00','17:00',false,480,ARRAY[0,1,2,3,4,5]::smallint[],10),
        ('NIGHT','Ca tối','Asia/Ho_Chi_Minh','18:00','03:00',true,480,ARRAY[0,1,2,3,4,5]::smallint[],20)
    """)
    op.execute("""
      INSERT INTO work_shift_intervals(shift_id,interval_type,start_minute,end_minute,label,sort_order)
      SELECT id,'WORK',480,720,'Ca sáng',10 FROM work_shifts WHERE code='DAY'
      UNION ALL SELECT id,'BREAK',720,780,'Nghỉ trưa',20 FROM work_shifts WHERE code='DAY'
      UNION ALL SELECT id,'WORK',780,1020,'Ca chiều',30 FROM work_shifts WHERE code='DAY'
      UNION ALL SELECT id,'WORK',1080,1320,'Đầu ca tối',10 FROM work_shifts WHERE code='NIGHT'
      UNION ALL SELECT id,'BREAK',1320,1380,'Nghỉ giữa ca',20 FROM work_shifts WHERE code='NIGHT'
      UNION ALL SELECT id,'WORK',1380,1620,'Cuối ca tối',30 FROM work_shifts WHERE code='NIGHT'
    """)
    op.execute("UPDATE system_meta SET value='65.8.29',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_table("work_shift_intervals")
    op.drop_table("work_shifts")
