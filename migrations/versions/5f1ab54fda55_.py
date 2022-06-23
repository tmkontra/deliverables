"""empty message

Revision ID: 5f1ab54fda55
Revises: 2a385a1f3e92
Create Date: 2022-06-22 20:18:30.495942

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f1ab54fda55'
down_revision = '2a385a1f3e92'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.create_unique_constraint("uniq_ili_deliverable_id", ['deliverable_id'])

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('invoice_line_item', schema=None) as batch_op:
        batch_op.drop_constraint("uniq_ili_deliverable_id", type_='unique')

    # ### end Alembic commands ###
