"""alter blackbox_requests incident_date to datetime

Revision ID: a102d3a203c4
Revises: 930d976038ba
Create Date: 2026-11-17 17:27:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a102d3a203c4'
down_revision: Union[str, None] = '930d976038ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'blackbox_requests',
        'incident_date',
        existing_type=sa.Date(),
        type_=sa.DateTime(),
        existing_nullable=True,
        postgresql_using='incident_date::timestamp',
    )


def downgrade() -> None:
    op.alter_column(
        'blackbox_requests',
        'incident_date',
        existing_type=sa.DateTime(),
        type_=sa.Date(),
        existing_nullable=True,
        postgresql_using='incident_date::date',
    )
