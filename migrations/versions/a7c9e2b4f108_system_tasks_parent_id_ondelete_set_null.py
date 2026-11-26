"""system_tasks parent_id ondelete set null

Revision ID: a7c9e2b4f108
Revises: d4e87ff2a3e1
Create Date: 2026-11-27 08:43:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7c9e2b4f108"
down_revision: Union[str, Sequence[str], None] = "d4e87ff2a3e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """system_tasks.parent_id 외래키에 ON DELETE SET NULL을 적용하여 만료 태스크 GC 삭제 충돌을 방지합니다."""
    op.drop_constraint("system_tasks_parent_id_fkey", "system_tasks", type_="foreignkey")
    op.create_foreign_key(
        "system_tasks_parent_id_fkey",
        "system_tasks",
        "system_tasks",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """기존 기본 외래키(NO ACTION)로 복원합니다."""
    op.drop_constraint("system_tasks_parent_id_fkey", "system_tasks", type_="foreignkey")
    op.create_foreign_key(
        "system_tasks_parent_id_fkey",
        "system_tasks",
        "system_tasks",
        ["parent_id"],
        ["id"],
    )
