"""allow display_num reuse after disposal

Revision ID: 26f6759edbab
Revises: 95619892acb6
Create Date: 2026-11-17 18:06:18.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26f6759edbab'
down_revision: Union[str, None] = '95619892acb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_blackbox_videos_display_num_active', table_name='blackbox_videos')
    op.create_index(
        'ix_blackbox_videos_display_num_active',
        'blackbox_videos',
        ['display_num'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false AND disposal_date IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_blackbox_videos_display_num_active', table_name='blackbox_videos')
    op.create_index(
        'ix_blackbox_videos_display_num_active',
        'blackbox_videos',
        ['display_num'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
    )
