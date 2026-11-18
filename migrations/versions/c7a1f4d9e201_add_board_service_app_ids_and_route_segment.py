"""add board service_app_ids and route_segment

Revision ID: c7a1f4d9e201
Revises: b59e03b2c729
Create Date: 2026-11-18 16:23:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7a1f4d9e201'
down_revision: Union[str, Sequence[str], None] = 'b59e03b2c729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    board_cols = {c['name'] for c in inspector.get_columns('board_config')}
    if 'service_app_ids' not in board_cols:
        op.add_column(
            'board_config',
            sa.Column(
                'service_app_ids',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                server_default='[]',
                nullable=True,
            ),
        )

    if 'route_segment' not in inspector.get_table_names():
        op.create_table(
            'route_segment',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('route_name', sa.String(length=100), nullable=False),
            sa.Column('route_master_id', sa.Integer(), nullable=True),
            sa.Column('seq', sa.Integer(), nullable=False),
            sa.Column('segment_name', sa.String(length=100), nullable=False),
            sa.Column('start_stop', sa.String(length=100), nullable=True),
            sa.Column('end_stop', sa.String(length=100), nullable=True),
            sa.Column('duration_min', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('distance_km', sa.String(length=20), nullable=True),
            sa.Column('memo', sa.String(length=200), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['route_master_id'], ['route_master.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_route_segment_route_name'), 'route_segment', ['route_name'], unique=False)
        op.create_index(op.f('ix_route_segment_route_master_id'), 'route_segment', ['route_master_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_route_segment_route_master_id'), table_name='route_segment')
    op.drop_index(op.f('ix_route_segment_route_name'), table_name='route_segment')
    op.drop_table('route_segment')
    op.drop_column('board_config', 'service_app_ids')
