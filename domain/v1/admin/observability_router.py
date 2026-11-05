"""
============================================================================
[통합 시스템 관제 및 감사로그 라우터 (domain/v1/admin/observability_router.py)]
============================================================================

💡 이 파일의 역할:
실시간 세션 감시(기존 sessions 기능 완벽 수용), 접속 이력, 앱 데이터 변경 감사(Diff), 
에러 및 보안 침해 로그를 단일 관제탑 화면에 제공하는 코어 API 라우터입니다.
"""

from datetime import datetime, date, timedelta
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database import get_db
from models import User, UserSession, AuditLog
from core.deps import require_app_permission
from core.audit import safe_log_audit
from core.config import settings
from redis_config import rd
from domain.user import user_crud
from domain.v1.admin.observability_schema import (
    AuditLogItemRes,
    AuditLogListRes,
    ObservabilitySummaryRes,
    LiveSessionItemRes,
)

logger = logging.getLogger("admin.observability")
router = APIRouter(prefix="/v1/admin/observability", tags=["Admin Observability"])

# 🏛️ AppRegistry 4단계 거버넌스 연동 (observability)
check_obs_read = require_app_permission("observability", action="read")
check_obs_write = require_app_permission("observability", action="write")


# ==========================================================================
# 🌐 1. 실시간 활성 세션 관제 (core/session.py 자가치유 정책 100% 일원화)
# ==========================================================================

def sync_expired_sessions(db: Session) -> int:
    """
    [세션 자가치유 및 만료 동기화 엔진 (core/session.py 정책 통일)]
    
    💡 원칙:
    1. DB를 단일 진실 공급원(SSOT)으로 삼습니다.
    2. 자연 만료 기간(SESSION_EXPIRE_DAYS)을 초과한 DB 세션만 EXPIRED 상태로 전환합니다.
    3. 유효 기간 내인데 Redis에서 휘발된 정상 세션은 오히려 Redis 키를 자가치유(Self-Healing) 복원하여
       사용자의 세션이 관제탑 조회로 인해 강제 종료되는 대형 사고를 원천 방어합니다.
    """
    active_sessions = (
        db.query(UserSession)
        .filter(UserSession.status == "ACTIVE")
        .all()
    )
    valid_count = 0
    now = datetime.now()
    expire_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    modified = False

    for s in active_sessions:
        # [1단계] DB 기준 실제 만료일 초과 여부 검사
        if s.last_activity and (now - s.last_activity) > expire_delta:
            s.status = "EXPIRED"
            s.logout_at = now
            modified = True
            continue

        # [2단계] 유효 세션: Redis 생존 확인 및 자가치유(Self-Healing)
        redis_key = f"session:{s.user_id}:{s.device_category}"
        try:
            if not rd.sismember(redis_key, s.session_key):
                # Redis가 재부팅되어 키가 없더라도 DB가 유효하므로 키를 안전하게 재등록
                rd.sadd(redis_key, s.session_key)
                rd.expire(redis_key, int(expire_delta.total_seconds()))
                logger.info(f"✨ [Observability] 세션 자가치유 복원: UID={s.user_id}, Session={s.session_key[:8]}...")
            else:
                # 살아있는 세션 TTL 슬라이딩 연장
                rd.expire(redis_key, int(expire_delta.total_seconds()))
        except Exception as re:
            logger.warning(f"⚠️ [Observability] Redis 일시 통신 오류, DB 세션 유지: {re}")

        valid_count += 1

    if modified:
        db.commit()

    return valid_count


@router.get(
    "/sessions",
    response_model=List[LiveSessionItemRes],
    summary="실시간 활성 세션 목록 조회"
)
def get_live_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
):
    """
    관리자 전용(admin_observability 앱 권한 필요):
    현재 시스템에 로그인되어 활동 중인 모든 기기/세션 목록을 실시간 조회하며,
    Redis 생존 여부를 대조하여 자가치유(Self-Healing) 복원 및 만료 세션을 정리합니다.
    """
    # 1. Redis 실시간 동기화 & 자가치유 (유령 세션만 EXPIRED 처리)
    sync_expired_sessions(db)

    # 2. 실제 살아있는 ACTIVE 세션만 로드
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
    target_session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_write)
):
    """
    관리자 전용(Rank 4 이상):
    의심 세션을 강제로 만료시키며(ID 또는 session_key 모두 지원), 감사로그(SECURITY)에 행위 이력을 즉시 영구 기록합니다.
    """
    result = user_crud.kick_session(db, session_id=target_session_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"세션 식별자 '{target_session_id}'을(를) 찾을 수 없습니다."
        )

    # 📜 [감사로그]: 관리자에 의한 세션 강제 추방 (SECURITY 로그)
    safe_log_audit(
        db=db,
        app_id="system",
        log_type="SECURITY",
        severity="WARN",
        action="SESSION_KICKED",
        title=f"관리자({current_user.username})에 의한 세션 #{result.id} 강제 추방",
        user=current_user,
        resource_type="user_session",
        resource_id=str(result.id),
        message=f"관리자 {current_user.username}(ID: {current_user.id})가 세션 #{result.id}을(를) 강제 종료시켰습니다.",
        metadata={"admin_id": current_user.id, "target_session_id": result.id, "session_key": result.session_key}
    )

    return {"message": "Success", "target_session_id": result.id}


# ==========================================================================
# 📊 2. 통합 감사로그 조회 & 통계 요약
# ==========================================================================

def _get_summary_stats(db: Session) -> ObservabilitySummaryRes:
    """오늘 기준 실시간 관제 요약 통계 집계"""
    today_start = datetime.combine(date.today(), datetime.min.time())

    # 1. 현재 활성 세션 수 (Redis 실시간 자기치유 동기화 반영)
    active_sessions = sync_expired_sessions(db)

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

    today_error_alert = today_errors + today_security

    return ObservabilitySummaryRes(
        active_sessions_count=active_sessions,
        today_logins_count=today_logins,
        today_changes_count=today_changes,
        today_errors_count=today_errors,
        today_security_count=today_security,
        # 🌟 프론트엔드(+page.svelte) 상단 요약 카드 호환
        active_sessions=active_sessions,
        today_access_count=today_logins,
        today_change_count=today_changes,
        today_error_alert_count=today_error_alert,
    )


@router.get(
    "/summary",
    response_model=ObservabilitySummaryRes,
    summary="관제탑 실시간 요약 통계 조회"
)
def get_observability_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
):
    """관리자 전용(admin_observability 앱 권한 필요): 상단 대시보드 배지용 실시간 요약 통계를 반환합니다."""
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
    skip: Optional[int] = Query(None, description="레거시 skip 파라미터 호환"),
    limit: Optional[int] = Query(None, description="레거시 limit 파라미터 호환"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
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

    # 페이징 계산: skip/limit 우선, 없으면 page/page_size 적용
    eff_offset = skip if skip is not None else ((page - 1) * page_size)
    eff_limit = limit if limit is not None else page_size

    items = (
        q.order_by(AuditLog.created_at.desc())
        .offset(eff_offset)
        .limit(eff_limit)
        .all()
    )

    summary = _get_summary_stats(db)

    return AuditLogListRes(
        items=items,
        total=total,
        page=page,
        page_size=eff_limit,
        summary=summary,
    )
