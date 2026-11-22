"""add_board_seq_and_next_seq

Revision ID: 66b60e3bf0d6
Revises: 96705d309d7f
Create Date: 2026-11-22 10:32:10.044318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '66b60e3bf0d6'
down_revision: Union[str, None] = '96705d309d7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with safe per-board sequence backfill."""
    op.add_column('board_config', sa.Column('next_seq', sa.Integer(), server_default='1', nullable=False))
    op.add_column('post', sa.Column('board_seq', sa.Integer(), nullable=True))

    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY board_id ORDER BY id ASC) AS seq
            FROM post
        )
        UPDATE post
        SET board_seq = ranked.seq
        FROM ranked
        WHERE post.id = ranked.id
    """)
    op.execute("""
        UPDATE board_config
        SET next_seq = COALESCE(
            (SELECT MAX(p.board_seq) FROM post p WHERE p.board_id = board_config.id),
            0
        ) + 1
    """)

    op.alter_column('post', 'board_seq', nullable=False)
    op.create_index(op.f('ix_post_board_seq'), 'post', ['board_seq'], unique=False)
    op.create_unique_constraint('uq_post_board_seq', 'post', ['board_id', 'board_seq'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_post_board_seq', 'post', type_='unique')
    op.drop_index(op.f('ix_post_board_seq'), table_name='post')
    op.drop_column('post', 'board_seq')
    op.drop_column('board_config', 'next_seq')
