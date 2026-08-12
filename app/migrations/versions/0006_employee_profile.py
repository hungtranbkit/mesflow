from alembic import op
import sqlalchemy as sa

revision='0006_employee_profile'
down_revision='0005_production_ops'
branch_labels=None
depends_on=None

def upgrade():
    additions = (
        ('team', sa.Text(), "''"),
        ('birth_date', sa.Date(), None),
        ('hometown', sa.Text(), "''"),
        ('phone', sa.Text(), "''"),
        ('identity_number', sa.Text(), "''"),
        ('identity_issue_date', sa.Date(), None),
        ('current_address', sa.Text(), "''"),
        ('start_date', sa.Date(), None),
        ('end_date', sa.Date(), None),
        ('contract_1', sa.Text(), "''"),
        ('contract_2', sa.Text(), "''"),
    )
    for name, column_type, default in additions:
        kwargs = {'nullable': True}
        if default is not None:
            kwargs.update(nullable=False, server_default=sa.text(default))
        op.add_column('employees', sa.Column(name, column_type, **kwargs))
    op.create_index('idx_employees_status_department_team', 'employees', ['employment_status','department','team'])

def downgrade():
    op.drop_index('idx_employees_status_department_team', table_name='employees')
    for name in ('contract_2','contract_1','end_date','start_date','current_address','identity_issue_date','identity_number','phone','hometown','birth_date','team'):
        op.drop_column('employees', name)
