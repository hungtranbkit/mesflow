"""Keep the default NIGHT shift within the selected business day, ending at midnight."""
from alembic import op

revision = "0026_night_shift_same_day_midnight"
down_revision = "0025_rbac_permissions"
branch_labels = None
depends_on = None

def upgrade():
    # Only migrate the original MESFlow default NIGHT shift. Custom user schedules
    # are intentionally left untouched.
    op.execute("""
    DO $$
    DECLARE sid bigint;
    BEGIN
      SELECT id INTO sid
      FROM work_shifts
      WHERE code='NIGHT'
        AND anchor_start='18:00'::time
        AND anchor_end='03:00'::time
        AND cross_midnight=true
      LIMIT 1;

      IF sid IS NOT NULL
         AND EXISTS (SELECT 1 FROM work_shift_intervals WHERE shift_id=sid AND start_minute=1080 AND end_minute=1320 AND interval_type='WORK')
         AND EXISTS (SELECT 1 FROM work_shift_intervals WHERE shift_id=sid AND start_minute=1320 AND end_minute=1380 AND interval_type='BREAK')
         AND EXISTS (SELECT 1 FROM work_shift_intervals WHERE shift_id=sid AND start_minute=1380 AND end_minute=1620 AND interval_type='WORK')
      THEN
        UPDATE work_shifts
        SET anchor_end='00:00'::time,
            cross_midnight=false,
            target_minutes=300,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=sid;

        UPDATE work_shift_intervals
        SET end_minute=1440
        WHERE shift_id=sid
          AND start_minute=1380
          AND end_minute=1620
          AND interval_type='WORK';
      END IF;
    END $$;
    """)
    op.execute("UPDATE system_meta SET value='65.8.44.46',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    # Do not rewrite a possibly edited production calendar on downgrade.
    pass
