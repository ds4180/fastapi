"""widen blackbox display_num to 3 chars

Revision ID: 95619892acb6
Revises: a102d3a203c4
Create Date: 2026-11-17 17:37:16.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95619892acb6'
down_revision: Union[str, None] = 'a102d3a203c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('blackbox_videos', 'display_num', existing_type=sa.String(length=2), type_=sa.String(length=3), existing_nullable=False)
    op.alter_column('blackbox_usages', 'display_num', existing_type=sa.String(length=2), type_=sa.String(length=3), existing_nullable=False)
    op.alter_column('blackbox_requests', 'current_display_num', existing_type=sa.String(length=2), type_=sa.String(length=3), existing_nullable=True)
    op.alter_column('blackbox_requests', 'replacement_display_num', existing_type=sa.String(length=2), type_=sa.String(length=3), existing_nullable=True)


def downgrade() -> None:
    op.alter_column('blackbox_requests', 'replacement_display_num', existing_type=sa.String(length=3), type_=sa.String(length=2), existing_nullable=True)
    op.alter_column('blackbox_requests', 'current_display_num', existing_type=sa.String(length=3), type_=sa.String(length=2), existing_nullable=True)
    op.alter_column('blackbox_usages', 'display_num', existing_type=sa.String(length=3), type_=sa.String(length=2), existing_nullable=False)
    op.alter_column('blackbox_videos', 'display_num', existing_type=sa.String(length=3), type_=sa.String(length=2), existing_nullable=False)
