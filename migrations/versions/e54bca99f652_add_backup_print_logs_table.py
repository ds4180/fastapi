"""add backup_print_logs table

Revision ID: e54bca99f652
Revises: a45f997ceff9
Create Date: 2026-11-17 15:41:21.918813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e54bca99f652'
down_revision: Union[str, None] = 'a45f997ceff9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'backup_print_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.String(length=100), nullable=False),
        sa.Column('app_name', sa.String(length=100), nullable=True),
        sa.Column('mode', sa.String(length=30), nullable=False),
        sa.Column('start_date', sa.String(length=20), nullable=True),
        sa.Column('end_date', sa.String(length=20), nullable=True),
        sa.Column('last_record_id', sa.Integer(), nullable=True),
        sa.Column('last_seq_no', sa.Integer(), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('fields', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('printed_by', sa.String(length=100), nullable=True),
        sa.Column('printed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_backup_print_logs_app_id'), 'backup_print_logs', ['app_id'], unique=False)
    op.create_index(op.f('ix_backup_print_logs_printed_at'), 'backup_print_logs', ['printed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_backup_print_logs_printed_at'), table_name='backup_print_logs')
    op.drop_index(op.f('ix_backup_print_logs_app_id'), table_name='backup_print_logs')
    op.drop_table('backup_print_logs')
