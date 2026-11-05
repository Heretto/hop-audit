"""deliverables build status and log

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-05 15:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('deliverables', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=16), server_default='idle', nullable=False))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('log', sa.JSON(), server_default='[]', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('deliverables', schema=None) as batch_op:
        batch_op.drop_column('log')
        batch_op.drop_column('error')
        batch_op.drop_column('started_at')
        batch_op.drop_column('status')
