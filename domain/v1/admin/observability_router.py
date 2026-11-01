"""
============================================================================
[통합 시스템 관제 및 감사로그 라우터 (domain/v1/admin/observability_router.py)]
============================================================================

💡 이 파일의 역할:
실시간 세션 감시(기존 sessions 기능 완벽 수용), 접속 이력, 앱 데이터 변경 감사(Diff), 
에러 및 보안 침해 로그를 단일 관제탑 화면에 제공하는 코어 API 라우터입니다.
"""

from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database import get_db
from models import User, UserSession, AuditLog
from core.deps import check_rank
from core.audit import safe_log_audit
from domain.user import user_crud
from domain.v1.admin.observability_schema import (
    AuditLogItemRes,
    AuditLogListRes,
    ObservabilitySummaryRes,
    LiveSessionItemRes,
)

router = APIRouter(prefix="/v1/admin/observability", tags=["Admin Observability"])


# ==========================================================================
# 🌐 1. 실시간 활성 세션 관제 (기존 /v1/admin/sessions 흡수·통합)
# ==========================================================================

@router.get(
    "/sessions",
    response_model=List[LiveSessionItemRes],
    summary="실시간 활성 세션 목록 조회"
)
def get_live_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """
    관리자 전용(Rank 4 이상):
    현재 시스템에 로그인되어 활동 중인 모든 기기/세션 목록을 실시간 조회합니다.
    """
    sessions = (
        db.query(UserSession)
        .join(User, UserSession.user_id == User.id)
        .filter(UserSession.status == "ACTIVE")
        .order_by(UserSession.last_activity.desc())
        .all()
    )

    items = []
    for s in sessions:
        user_name = s.user.username if s.user else "Unknown"
        items.append(
            LiveSessionItemRes(
                id=s.id,
                session_key=s.session_key,
                user_id=s.user_id,
                username=user_name,
                device_category=s.device_category,
                status=s.status,
                device_name=s.device_name,
                ip_address=s.ip_address,
                login_at=s.login_at,
                last_activity=s.last_activity,
            )
        )
    return items


@router.post(
    "/sessions/kick/{target_session_id}",
    summary="특정 세션 강제 추방 (원클릭 KICK)"
)
def kick_session(
    target_session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """
    관리자 전용(Rank 4 이상):
    의심 세션을 강제로 만료시키며, 감사로그(SECURITY)에 행위 이력을 즉시 영구 기록합니다.
    """
    result = user_crud.kick_session(db, session_id=target_session_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"세션 ID {target_session_id}을(를) 찾을 수 없습니다."
        )

    # 📜 [감사로그]: 관리자에 의한 세션 강제 추방 (SECURITY 로그)
    safe_log_audit(
        db=db,
        app_id="system",
        log_type="SECURITY",
        severity="WARN",
        action="SESSION_KICKED",
        title=f"관리자({current_user.username})에 의한 세션 #{target_session_id} 강제 추방",
        user=current_user,
        resource_type="user_session",
        resource_id=str(target_session_id),
        message=f"관리자 {current_user.username}(ID: {current_user.id})가 세션 #{target_session_id}을(를) 강제 종료시켰습니다.",
        metadata={"admin_id": current_user.id, "target_session_id": target_session_id}
    )

    return {"message": "Success", "target_session_id": target_session_id}


# ==========================================================================
# 📊 2. 통합 감사로그 조회 & 통계 요약
# ==========================================================================

def _get_summary_stats(db: Session) -> ObservabilitySummaryRes:
    """오늘 기준 실시간 관제 요약 통계 집계"""
    today_start = datetime.combine(date.today(), datetime.min.time())

    # 1. 현재 활성 세션 수
    active_sessions = db.query(func.count(UserSession.id)).filter(UserSession.status == "ACTIVE").scalar() or 0

    # 2. 오늘 로그인 수 (ACCESS & LOGIN_SUCCESS)
    today_logins = db.query(func.count(AuditLog.id)).filter(
        AuditLog.log_type == "ACCESS",
        AuditLog.action == "LOGIN_SUCCESS",
        AuditLog.created_at >= today_start
    ).scalar() or 0

    # 3. 오늘 데이터 변경 수 (CHANGE)
    today_changes = db.query(func.count(AuditLog.id)).filter(
        AuditLog.log_type == "CHANGE",
        AuditLog.created_at >= today_start
    ).scalar() or 0

    # 4. 오늘 에러 건수 (ERROR)
    today_errors = db.query(func.count(AuditLog.id)).filter(
        AuditLog.log_type == "ERROR",
        AuditLog.created_at >= today_start
    ).scalar() or 0

    # 5. 오늘 보안 침해 건수 (SECURITY)
    today_security = db.query(func.count(AuditLog.id)).filter(
        AuditLog.log_type == "SECURITY",
        AuditLog.created_at >= today_start
    ).scalar() or 0

    return ObservabilitySummaryRes(
        active_sessions_count=active_sessions,
        today_logins_count=today_logins,
        today_changes_count=today_changes,
        today_errors_count=today_errors,
        today_security_count=today_security,
    )


@router.get(
    "/summary",
    response_model=ObservabilitySummaryRes,
    summary="관제탑 실시간 요약 통계 조회"
)
def get_observability_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """관리자 전용: 상단 대시보드 배지용 실시간 요약 통계를 반환합니다."""
    return _get_summary_stats(db)


@router.get(
    "/logs",
    response_model=AuditLogListRes,
    summary="전사 통합 감사로그 페이징 및 필터 검색"
)
def get_audit_logs(
    app_id: Optional[str] = Query(None, description="앱 식별자 필터 (예: 'dispatch', 'auth', 'board')"),
    log_type: Optional[str] = Query(None, description="'ACCESS' | 'CHANGE' | 'ERROR' | 'SECURITY'"),
    severity: Optional[str] = Query(None, description="'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'"),
    user_id: Optional[int] = Query(None, description="특정 사용자 user_id 필터"),
    query: Optional[str] = Query(None, description="제목, 내용, 사용자 스냅샷 검색어"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지당 건수 (최대 100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """
    관리자 전용(Rank 4 이상):
    전사 감사로그를 앱별, 유형별, 심각도별, 사용자별로 고속 필터링하여 페이징 조회합니다.
    """
    q = db.query(AuditLog)

    if app_id:
        q = q.filter(AuditLog.app_id == app_id)
    if log_type:
        q = q.filter(AuditLog.log_type == log_type.upper())
    if severity:
        q = q.filter(AuditLog.severity == severity.upper())
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if query:
        search_pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                AuditLog.title.ilike(search_pattern),
                AuditLog.message.ilike(search_pattern),
                AuditLog.user_summary.ilike(search_pattern),
            )
        )

    total = q.count()
    items = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    summary = _get_summary_stats(db)

    return AuditLogListRes(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        summary=summary,
    )
