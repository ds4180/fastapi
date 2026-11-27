"""add hot path indexes for tasks miniapp dispatch

Revision ID: c3f1a8d92e41
Revises: a7c9e2b4f108
Create Date: 2026-11-27 10:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f1a8d92e41"
down_revision: Union[str, Sequence[str], None] = "a7c9e2b4f108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """고빈도 워커 폴링·알람 감시·GC·배차 통계용 핵심 부분/복합 인덱스 추가"""
    # 1. 워커 2초 폴링(PENDING 선점) 전용 부분 복합 인덱스
    op.create_index(
        "ix_system_tasks_pending_poll",
        "system_tasks",
        ["scheduled_at", "priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
        if_not_exists=True,
    )
    # 2. parent_id FK (ON DELETE SET NULL) 및 연쇄 정리 가속용 인덱스
    op.create_index(
        "ix_system_tasks_parent_id",
        "system_tasks",
        ["parent_id"],
        unique=False,
        if_not_exists=True,
    )
    # 3. 보존 GC 및 최근 24시간 완료 집계용 복합 인덱스
    op.create_index(
        "ix_system_tasks_status_completed",
        "system_tasks",
        ["status", "completed_at"],
        unique=False,
        if_not_exists=True,
    )
    # 4. 1분 주기 미니앱 알람 감시(CHECK_MINIAPP_ALARMS) 풀스캔 제거용 부분 인덱스
    op.create_index(
        "ix_miniapp_items_pending_alarms",
        "miniapp_items",
        ["target_time"],
        unique=False,
        postgresql_where=sa.text("category = 'ALARM' AND status = 'PENDING' AND target_time IS NOT NULL"),
        if_not_exists=True,
    )
    # 5. 기사별 배차·근무 통계 조회 가속용 복합 인덱스
    op.create_index(
        "ix_dispatch_driver_date",
        "dispatch",
        ["driver_name", "target_date"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_dispatch_driver_date", table_name="dispatch", if_exists=True)
    op.drop_index("ix_miniapp_items_pending_alarms", table_name="miniapp_items", if_exists=True)
    op.drop_index("ix_system_tasks_status_completed", table_name="system_tasks", if_exists=True)
    op.drop_index("ix_system_tasks_parent_id", table_name="system_tasks", if_exists=True)
    op.drop_index("ix_system_tasks_pending_poll", table_name="system_tasks", if_exists=True)
