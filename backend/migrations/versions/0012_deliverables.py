"""deliverables

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-04 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('deliverables',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('copy', sa.JSON(), nullable=False),
    sa.Column('counts', sa.JSON(), nullable=False),
    sa.Column('heights', sa.JSON(), nullable=False),
    sa.Column('spot_checked', sa.Boolean(), nullable=False),
    sa.Column('marketing_ok', sa.Boolean(), nullable=False),
    sa.Column('agent_name', sa.String(length=255), nullable=False),
    sa.Column('built_by', sa.String(length=255), nullable=True),
    sa.Column('built_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['audit_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id')
    )
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prospect_logo', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.drop_column('prospect_logo')
    op.drop_table('deliverables')
