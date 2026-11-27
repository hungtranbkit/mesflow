"""Persist a stable, short decimal number for each hardware kiosk."""
from alembic import op
import sqlalchemy as sa

revision = '0057_kiosk_display_number'
down_revision = '0056_kiosk_enrollment_approval'
branch_labels = None
depends_on = None


def upgrade():
    # No nextval DEFAULT: register/bind use INSERT ... ON CONFLICT, whose
    # repeated attempts must not consume a new human number every time.
    op.add_column('kiosk_identities', sa.Column('display_number', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_kiosk_identity_display_number', 'kiosk_identities', ['display_number'])
    op.create_check_constraint('ck_kiosk_display_number_range', 'kiosk_identities',
                               'display_number BETWEEN 1 AND 2147483647')
    op.execute("""CREATE SEQUENCE kiosk_display_number_seq AS INTEGER
        MINVALUE 1 MAXVALUE 2147483647 NO CYCLE
        OWNED BY kiosk_identities.display_number""")
    # This is a one-time historical inventory assignment. Sorting the UI,
    # renaming, disabling or reconnecting never recomputes these values.
    # New unapproved devices are numbered only after an authorized activation.
    op.execute("""WITH numbered AS (
        SELECT id,row_number() OVER (ORDER BY created_at,id)::integer AS number
        FROM kiosk_identities WHERE upper(device_uuid) NOT LIKE 'WEB-%'
    ) UPDATE kiosk_identities ki SET display_number=numbered.number
      FROM numbered WHERE ki.id=numbered.id""")
    op.execute("""SELECT setval('kiosk_display_number_seq',
        COALESCE(MAX(display_number),1),COUNT(display_number)>0)
        FROM kiosk_identities""")


def downgrade():
    # Application rollback keeps this additive schema. An explicit database
    # downgrade removes the human numbers, but never identity/token records.
    op.execute('DROP SEQUENCE kiosk_display_number_seq')
    op.drop_constraint('ck_kiosk_display_number_range', 'kiosk_identities', type_='check')
    op.drop_constraint('uq_kiosk_identity_display_number', 'kiosk_identities', type_='unique')
    op.drop_column('kiosk_identities', 'display_number')
