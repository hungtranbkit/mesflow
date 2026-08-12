from alembic import op
import sqlalchemy as sa
revision='0002_master_data'
down_revision='0001_core'
branch_labels=None
depends_on=None

def timestamps():
    return (
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('CURRENT_TIMESTAMP')),
    )

def upgrade():
    op.create_table('employees',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('employee_no',sa.Text(),nullable=False,unique=True),
        sa.Column('name',sa.Text(),nullable=False),
        sa.Column('department',sa.Text(),nullable=False,server_default=''),
        sa.Column('position',sa.Text(),nullable=False,server_default=''),
        sa.Column('employment_status',sa.Text(),nullable=False,server_default='Đang làm'),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),
        sa.Column('qr',sa.Text(),nullable=False,unique=True),*timestamps())
    op.create_index('idx_employees_active_department','employees',['active','department'])

    op.create_table('stations',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('code',sa.Text(),nullable=False,unique=True),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('workshop',sa.Text(),nullable=False,server_default=''),
        sa.Column('production_line',sa.Text(),nullable=False,server_default=''),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),*timestamps())

    op.create_table('equipment',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('code',sa.Text(),nullable=False,unique=True),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('equipment_type',sa.Text(),nullable=False,server_default=''),
        sa.Column('status',sa.Text(),nullable=False,server_default='ACTIVE'),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),
        sa.Column('notes',sa.Text(),nullable=False,server_default=''),*timestamps())

    op.create_table('sales_orders',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('code',sa.Text(),nullable=False,unique=True),
        sa.Column('customer_name',sa.Text(),nullable=False),
        sa.Column('contract_no',sa.Text(),nullable=False,server_default=''),
        sa.Column('status',sa.Text(),nullable=False,server_default='DRAFT'),
        sa.Column('priority',sa.Text(),nullable=False,server_default='NORMAL'),
        sa.Column('delivery_deadline',sa.Date()),sa.Column('notes',sa.Text(),nullable=False,server_default=''),*timestamps())

    op.create_table('production_orders',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('code',sa.Text(),nullable=False,unique=True),
        sa.Column('sales_order_id',sa.BigInteger(),sa.ForeignKey('sales_orders.id',ondelete='SET NULL')),
        sa.Column('product',sa.Text(),nullable=False),
        sa.Column('planned_quantity',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('status',sa.Text(),nullable=False,server_default='PLANNED'),
        sa.Column('priority',sa.Text(),nullable=False,server_default='NORMAL'),
        sa.Column('due_date',sa.Date()),sa.Column('notes',sa.Text(),nullable=False,server_default=''),*timestamps())
    op.create_index('idx_po_status_due','production_orders',['status','due_date'])

    op.create_table('parts',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('production_order_id',sa.BigInteger(),sa.ForeignKey('production_orders.id',ondelete='CASCADE'),nullable=False),
        sa.Column('code',sa.Text(),nullable=False),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('drawing_path',sa.Text(),nullable=False,server_default=''),
        sa.Column('sort_order',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),*timestamps(),
        sa.UniqueConstraint('production_order_id','code',name='uq_parts_po_code'))

    op.create_table('operations',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('production_order_id',sa.BigInteger(),sa.ForeignKey('production_orders.id',ondelete='CASCADE'),nullable=False),
        sa.Column('part_id',sa.BigInteger(),sa.ForeignKey('parts.id',ondelete='CASCADE'),nullable=False),
        sa.Column('equipment_id',sa.BigInteger(),sa.ForeignKey('equipment.id',ondelete='SET NULL')),
        sa.Column('code',sa.Text(),nullable=False,unique=True),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('plan_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('done_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('defect_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('status',sa.Text(),nullable=False,server_default='PLANNED'),
        sa.Column('sort_order',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('qr',sa.Text(),nullable=False,unique=True),*timestamps())
    op.create_index('idx_operations_po_part','operations',['production_order_id','part_id','sort_order'])

    op.create_table('templates',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('code',sa.Text(),nullable=False,unique=True),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('product',sa.Text(),nullable=False,server_default=''),
        sa.Column('version',sa.Text(),nullable=False,server_default='1.0'),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.text('true')),
        sa.Column('source_workbook',sa.Text(),nullable=False,server_default=''),*timestamps())
    op.create_table('template_parts',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('template_id',sa.BigInteger(),sa.ForeignKey('templates.id',ondelete='CASCADE'),nullable=False),
        sa.Column('code',sa.Text(),nullable=False,server_default=''),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('sort_order',sa.Integer(),nullable=False,server_default='0'))
    op.create_table('template_operations',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('template_id',sa.BigInteger(),sa.ForeignKey('templates.id',ondelete='CASCADE'),nullable=False),
        sa.Column('part_id',sa.BigInteger(),sa.ForeignKey('template_parts.id',ondelete='CASCADE')),
        sa.Column('code',sa.Text(),nullable=False,server_default=''),sa.Column('name',sa.Text(),nullable=False),
        sa.Column('plan_qty',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('sort_order',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('equipment_code',sa.Text(),nullable=False,server_default=''))
    op.create_table('template_equipment',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('template_id',sa.BigInteger(),sa.ForeignKey('templates.id',ondelete='CASCADE'),nullable=False),
        sa.Column('equipment_id',sa.BigInteger(),sa.ForeignKey('equipment.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('quantity',sa.Integer(),nullable=False,server_default='1'),
        sa.UniqueConstraint('template_id','equipment_id',name='uq_template_equipment'))

    op.execute("UPDATE system_meta SET value='65.1.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    for name in ('template_equipment','template_operations','template_parts','templates','operations','parts','production_orders','sales_orders','equipment','stations','employees'):
        op.drop_table(name)
