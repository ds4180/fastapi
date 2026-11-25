from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.deps import require_app_permission
from database import get_db
from domain.system.app_service import migrate_boards_to_board
from models import (
    AppRegistry,
    AuditLog,
    BoardConfig,
    DayOff,
    MiniappItem,
    Post,
    SystemTask,
    User,
    UserProfile,
    UserSession,
)

router = APIRouter()

check_admin = require_app_permission("dashboard", action="read")


@router.get("/dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin),
):
    """
    [코어 통합 관제탑 대시보드 요약 정보]
    시스템 코어 엔진(자율신경계 태스크, 관제/감사로그, 세션/근무, 지시사항 인지율) 종합 지표
    """
    migrate_boards_to_board(db)
    now = datetime.now()
    today = now.date()
    yesterday = now - timedelta(hours=24)

    # 1. 자율신경계 태스크 상태
    task_pending = db.query(SystemTask).filter(SystemTask.status == "PENDING").count()
    task_running = db.query(SystemTask).filter(SystemTask.status == "RUNNING").count()
    task_failed = db.query(SystemTask).filter(SystemTask.status == "FAILED").count()
    next_task = (
        db.query(SystemTask.scheduled_at)
        .filter(SystemTask.status == "PENDING")
        .order_by(SystemTask.scheduled_at.asc())
        .first()
    )
    next_task_str = next_task[0].strftime("%Y-%m-%d %H:%M") if next_task and next_task[0] else None

    # 2. 통합 관제 & 감사로그 (최근 24시간 보안 침해 및 시스템 에러)
    security_breach_24h = (
        db.query(AuditLog)
        .filter(
            AuditLog.log_type == "SECURITY",
            AuditLog.created_at >= yesterday,
        )
        .count()
    )
    error_log_24h = (
        db.query(AuditLog)
        .filter(
            AuditLog.log_type == "ERROR",
            AuditLog.created_at >= yesterday,
        )
        .count()
    )

    # 실시간 활성 세션 (Active Sessions)
    active_sessions = db.query(UserSession).filter(UserSession.status == "ACTIVE").count()

    # 3. 오늘 근무 및 휴무 비율
    dayoff_count = (
        db.query(DayOff)
        .filter(
            DayOff.date == today,
            DayOff.status == "APPROVED",
            DayOff.is_deleted == False,
        )
        .count()
    )
    active_user_count = db.query(UserProfile).filter(UserProfile.is_active == True).count()
    working_count = max(0, active_user_count - dayoff_count)

    # 4. 현장 지시사항 미확인 인지율 감시
    unconfirmed_instructions = (
        db.query(MiniappItem)
        .filter(
            MiniappItem.category == "INSTRUCTION",
            MiniappItem.status.notin_(["CONFIRMED", "COMPLETED"]),
        )
        .count()
    )

    # 5. 기존 기본 메타 카운트 (하위 호환성 100% 유지)
    user_count = db.query(User).count()
    board_count = db.query(BoardConfig).count()
    post_count = db.query(Post).count()
    app_count = db.query(AppRegistry).count()

    # 6. 실시간 시스템/비즈니스 앱 권한 메타데이터 (AppRegistry 실시간 연동)
    all_registered_apps = db.query(AppRegistry).order_by(AppRegistry.app_id.asc()).all()
    apps_meta = [
        {
            "app_id": a.app_id,
            "name": a.name,
            "title": a.title,
            "description": a.description,
            "app_type": a.app_type or "CUSTOM",
            "icon_default": a.icon_default,
            "frontend_route": a.frontend_route,
            "min_read_rank": a.min_read_rank if a.min_read_rank is not None else 4,
            "min_write_rank": a.min_write_rank if a.min_write_rank is not None else 4,
            "allow_groups": a.allow_groups or [],
            "deny_groups": a.deny_groups or [],
            "is_active": a.is_active,
        }
        for a in all_registered_apps
    ]

    return {
        "admin_name": admin.real_name or admin.username,
        "task_engine": {
            "is_healthy": task_failed == 0,
            "pending_count": task_pending,
            "running_count": task_running,
            "failed_count": task_failed,
            "next_scheduled_task": next_task_str,
        },
        "observability": {
            "security_breach_24h": security_breach_24h,
            "error_log_24h": error_log_24h,
            "active_sessions": active_sessions,
        },
        "duty_status": {
            "working_count": working_count,
            "dayoff_count": dayoff_count,
            "active_user_count": active_user_count,
        },
        "instruction_watchdog": {
            "unconfirmed_count": unconfirmed_instructions,
        },
        "watchdog_status": {
            "enabled": True,
            "fail_threshold": 3,
            "security_alert": True,
        },
        # 하위 호환 필드
        "user_count": user_count,
        "board_count": board_count,
        "post_count": post_count,
        "app_count": app_count,
        # 실시간 앱 권한 명부
        "system_apps": apps_meta,
    }
