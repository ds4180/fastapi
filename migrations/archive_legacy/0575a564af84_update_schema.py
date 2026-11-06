"""update_schema

Revision ID: 0575a564af84
Revises: d83da6075629
Create Date: 2026-05-22 14:35:36.004543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0575a564af84'
down_revision: Union[str, None] = 'd83da6075629'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
