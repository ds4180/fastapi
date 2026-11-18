"""add dayoff_policy table

Revision ID: d8e2a3b4c5f6
Revises: c7a1f4d9e201
Create Date: 2026-11-18 16:57:10.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd8e2a3b4c5f6'
down_revision: Union[str, Sequence[str], None] = 'c7a1f4d9e201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'dayoff_policy' not in inspector.get_table_names():
        op.create_table(
            'dayoff_policy',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('effective_date', sa.Date(), nullable=False),
            sa.Column('classify_mode', sa.String(length=20), nullable=False, server_default='BOTH'),
            sa.Column(
                'fcfs_groups',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                nullable=False,
                server_default='[]',
            ),
            sa.Column(
                'fcfs_ranks',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                nullable=False,
                server_default='[]',
            ),
            sa.Column('daily_quota', sa.Integer(), nullable=False, server_default='3'),
            sa.Column(
                'date_overrides',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                nullable=False,
                server_default='{}',
            ),
            sa.Column('max_monthly_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('max_days_per_request', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('min_advance_days', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('max_advance_days', sa.Integer(), nullable=False, server_default='0'),
            sa.Column(
                'etc',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                nullable=False,
                server_default='{}',
            ),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('create_date', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_dayoff_policy_effective_date'), 'dayoff_policy', ['effective_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dayoff_policy_effective_date'), table_name='dayoff_policy')
    op.drop_table('dayoff_policy')
