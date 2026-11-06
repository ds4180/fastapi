"""add_menu_app_and_alert_columns

Revision ID: f4a8b2c9d1e3
Revises: c7e2b1f890ab
Create Date: 2026-11-06 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f4a8b2c9d1e3'
down_revision: Union[str, None] = 'c7e2b1f890ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema with menu, app_registry, and alert permission columns."""
    
    # 1. menu 테이블 컬럼 추가
    if not column_exists('menu', 'allow_groups'):
        op.add_column('menu', sa.Column('allow_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    if not column_exists('menu', 'deny_groups'):
        op.add_column('menu', sa.Column('deny_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))

    # 2. app_registry 테이블 컬럼 추가
    if not column_exists('app_registry', 'allow_groups'):
        op.add_column('app_registry', sa.Column('allow_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    if not column_exists('app_registry', 'deny_groups'):
        op.add_column('app_registry', sa.Column('deny_groups', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))

    # 3. alert 테이블 컬럼 추가
    if not column_exists('alert', 'target_group'):
        op.add_column('alert', sa.Column('target_group', sa.String(length=50), nullable=True))
    if not column_exists('alert', 'category'):
        op.add_column('alert', sa.Column('category', sa.String(length=20), server_default='GENERAL', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    if column_exists('alert', 'category'):
        op.drop_column('alert', 'category')
    if column_exists('alert', 'target_group'):
        op.drop_column('alert', 'target_group')

    if column_exists('app_registry', 'deny_groups'):
        op.drop_column('app_registry', 'deny_groups')
    if column_exists('app_registry', 'allow_groups'):
        op.drop_column('app_registry', 'allow_groups')

    if column_exists('menu', 'deny_groups'):
        op.drop_column('menu', 'deny_groups')
    if column_exists('menu', 'allow_groups'):
        op.drop_column('menu', 'allow_groups')
