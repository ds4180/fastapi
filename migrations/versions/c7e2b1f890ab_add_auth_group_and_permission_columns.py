"""add_auth_group_and_permission_columns

Revision ID: c7e2b1f890ab
Revises: 0575a564af84
Create Date: 2026-11-06 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7e2b1f890ab'
down_revision: Union[str, None] = '0575a564af84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema with 4-tier auth and permission columns."""
    
    # 1. user_profiles 테이블 컬럼 추가
    if not column_exists('user_profiles', 'primary_group'):
        op.add_column('user_profiles', sa.Column('primary_group', sa.String(length=50), nullable=True))
    if not column_exists('user_profiles', 'secondary_groups'):
        op.add_column('user_profiles', sa.Column('secondary_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))

    # 2. board_config 테이블 컬럼 추가
    if not column_exists('board_config', 'min_read_rank'):
        op.add_column('board_config', sa.Column('min_read_rank', sa.Integer(), server_default='0', nullable=False))
    if not column_exists('board_config', 'min_write_rank'):
        op.add_column('board_config', sa.Column('min_write_rank', sa.Integer(), server_default='2', nullable=False))
    if not column_exists('board_config', 'allow_groups'):
        op.add_column('board_config', sa.Column('allow_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    if not column_exists('board_config', 'deny_groups'):
        op.add_column('board_config', sa.Column('deny_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))

    # 3. page 테이블 컬럼 추가
    if not column_exists('page', 'allow_groups'):
        op.add_column('page', sa.Column('allow_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    if not column_exists('page', 'deny_groups'):
        op.add_column('page', sa.Column('deny_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    if column_exists('page', 'deny_groups'):
        op.drop_column('page', 'deny_groups')
    if column_exists('page', 'allow_groups'):
        op.drop_column('page', 'allow_groups')

    if column_exists('board_config', 'deny_groups'):
        op.drop_column('board_config', 'deny_groups')
    if column_exists('board_config', 'allow_groups'):
        op.drop_column('board_config', 'allow_groups')
    if column_exists('board_config', 'min_write_rank'):
        op.drop_column('board_config', 'min_write_rank')
    if column_exists('board_config', 'min_read_rank'):
        op.drop_column('board_config', 'min_read_rank')

    if column_exists('user_profiles', 'secondary_groups'):
        op.drop_column('user_profiles', 'secondary_groups')
    if column_exists('user_profiles', 'primary_group'):
        op.drop_column('user_profiles', 'primary_group')
