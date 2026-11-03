"""content-integrity categories per run

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('audit_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('integrity_categories', sa.JSON(), nullable=True))
    with op.batch_alter_table('claim_group_reviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('categories', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('claim_group_reviews', schema=None) as batch_op:
        batch_op.drop_column('categories')
    with op.batch_alter_table('audit_runs', schema=None) as batch_op:
        batch_op.drop_column('integrity_categories')
