"""add schedules table

Revision ID: d660c0655de1
Revises: 26f6759edbab
Create Date: 2026-11-17 19:11:36.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd660c0655de1'
down_revision: Union[str, None] = '26f6759edbab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=True),
        sa.Column('is_all_day', sa.Boolean(), nullable=False),
        sa.Column('display_mode', sa.String(length=20), nullable=False),
        sa.Column('importance', sa.Integer(), nullable=False),
        sa.Column('is_dday', sa.Boolean(), nullable=False),
        sa.Column('recurrence_rule', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_schedules_id'), 'schedules', ['id'], unique=False)
    op.create_index(op.f('ix_schedules_user_id'), 'schedules', ['user_id'], unique=False)
    op.create_index(op.f('ix_schedules_category'), 'schedules', ['category'], unique=False)
    op.create_index(op.f('ix_schedules_scope'), 'schedules', ['scope'], unique=False)
    op.create_index(op.f('ix_schedules_start_at'), 'schedules', ['start_at'], unique=False)
    op.create_index(op.f('ix_schedules_end_at'), 'schedules', ['end_at'], unique=False)
    op.create_index(op.f('ix_schedules_is_deleted'), 'schedules', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_schedules_is_deleted'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_end_at'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_start_at'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_scope'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_category'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_user_id'), table_name='schedules')
    op.drop_index(op.f('ix_schedules_id'), table_name='schedules')
    op.drop_table('schedules')
