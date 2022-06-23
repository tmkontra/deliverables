"""empty message

Revision ID: eace6f0b0521
Revises: 5f1ab54fda55
Create Date: 2022-06-22 20:22:10.341566

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eace6f0b0521'
down_revision = '5f1ab54fda55'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
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

    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DECIMAL(),
               nullable=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DECIMAL(),
               nullable=True)

    with op.batch_alter_table('invoice_reimbursement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_reimbursement_id'))

    op.drop_table('invoice_reimbursement')
    with op.batch_alter_table('invoice_credit', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_credit_id'))

    op.drop_table('invoice_credit')
    # ### end Alembic commands ###
