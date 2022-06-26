"""empty message

Revision ID: 20ae18b6f647
Revises: 
Create Date: 2022-06-25 22:46:56.263438

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20ae18b6f647'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('bill_to',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_name', sa.String(), nullable=False),
    sa.Column('contact_name', sa.String(), nullable=False),
    sa.Column('contact_email', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bill_to', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bill_to_id'), ['id'], unique=False)

    op.create_table('project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('bill_to_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['bill_to_id'], ['bill_to.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_project_name'), ['name'], unique=True)

    op.create_table('deliverable',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('estimate', sa.DECIMAL(), nullable=True),
    sa.Column('created', sa.DATETIME(), nullable=False),
    sa.Column('due_date', sa.DATE(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('deliverable', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deliverable_id'), ['id'], unique=False)

    op.create_table('invoice',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('sent', sa.DATE(), nullable=True),
    sa.Column('paid', sa.DATE(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('invoice', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoice_id'), ['id'], unique=False)

    op.create_table('invoice_credit',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('amount', sa.DECIMAL(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('invoice_credit', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoice_credit_id'), ['id'], unique=False)

    op.create_table('invoice_line_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('deliverable_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.DECIMAL(), nullable=False),
    sa.ForeignKeyConstraint(['deliverable_id'], ['deliverable.id'], ),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('deliverable_id')
    )
    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoice_line_item_id'), ['id'], unique=False)

    op.create_table('invoice_reimbursement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('amount', sa.DECIMAL(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('invoice_reimbursement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoice_reimbursement_id'), ['id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('invoice_reimbursement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_reimbursement_id'))

    op.drop_table('invoice_reimbursement')
    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_line_item_id'))

    op.drop_table('invoice_line_item')
    with op.batch_alter_table('invoice_credit', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_credit_id'))

    op.drop_table('invoice_credit')
    with op.batch_alter_table('invoice', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_id'))

    op.drop_table('invoice')
    with op.batch_alter_table('deliverable', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deliverable_id'))

    op.drop_table('deliverable')
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_name'))
        batch_op.drop_index(batch_op.f('ix_project_id'))

    op.drop_table('project')
    with op.batch_alter_table('bill_to', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bill_to_id'))

    op.drop_table('bill_to')
    # ### end Alembic commands ###
