"""
============================================================================
[통합 시스템 관제 및 감사로그 라우터 (domain/v1/admin/observability_router.py)]
============================================================================

💡 이 파일의 역할:
실시간 세션 감시(기존 sessions 기능 완벽 수용), 접속 이력, 앱 데이터 변경 감사(Diff), 
에러 및 보안 침해 로그를 단일 관제탑 화면에 제공하는 코어 API 라우터입니다.
"""

from datetime import datetime, date
import logging
import csv
import io
import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database import get_db
from models import User, UserSession, AuditLog
from core.deps import require_app_permission
from core.audit import safe_log_audit
from core.session import sync_expired_sessions
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
# 🌐 1. 실시간 활성 세션 관제 (core/session.py 통합 자가치유 엔진 재사용)
# ==========================================================================


@router.get(
    "/sessions",
    response_model=List[LiveSessionItemRes],
    summary="실시간 활성 세션 및 접속 이력 목록 조회"
)
def get_live_sessions(
    include_history: bool = Query(False, description="과거 만료/종료된 세션 접속 이력까지 전체 포함 여부"),
    limit: int = Query(100, description="최대 조회 건수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
):
    """
    관리자 전용(admin_observability 앱 권한 필요):
    현재 시스템에 로그인되어 활동 중인 실시간 세션(ACTIVE)을 조회합니다.
    include_history=True 일 경우 과거 로그아웃/만료/추방된 세션 접속 기록(EXPIRED, KICKED_OUT)까지 함께 조회합니다.
    """
    # 1. Redis 실시간 동기화 & 자가치유 (유령 세션만 EXPIRED 처리)
    sync_expired_sessions(db)

    # 2. 세션 쿼리 (include_history 여부에 따라 분기)
    query = (
        db.query(UserSession)
        .join(User, UserSession.user_id == User.id)
    )

    if not include_history:
        query = query.filter(UserSession.status == "ACTIVE")

    sessions = query.order_by(UserSession.last_activity.desc()).limit(limit).all()

    items = []
    for s in sessions:
        user_name = s.user.username if s.user else "Unknown"
        real_name = s.user.real_name if s.user and s.user.real_name else ""
        profile = s.user.profile if s.user else None
        p_grp = profile.primary_group if profile and profile.primary_group else None

        items.append(
            LiveSessionItemRes(
                id=s.id,
                session_key=s.session_key,
                user_id=s.user_id,
                username=user_name,
                real_name=real_name,
                primary_group=p_grp,
                device_category=s.device_category,
                status=s.status,
                device_name=s.device_name,
                ip_address=s.ip_address,
                login_at=s.login_at,
                logout_at=s.logout_at,
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


# ==========================================================================
# 📥 3. 전사 감사로그 CSV 내보내기 & 시스템 원시 로그 다운로드
# ==========================================================================

@router.get(
    "/logs/export",
    summary="전사 감사로그 CSV 내보내기 다운로드"
)
def export_audit_logs_csv(
    app_id: Optional[str] = Query(None, description="앱 식별자 필터"),
    log_type: Optional[str] = Query(None, description="'ACCESS' | 'CHANGE' | 'ERROR' | 'SECURITY'"),
    severity: Optional[str] = Query(None, description="'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'"),
    user_id: Optional[int] = Query(None, description="특정 사용자 user_id 필터"),
    query: Optional[str] = Query(None, description="검색어"),
    limit: int = Query(5000, ge=1, le=20000, description="내보낼 최대 건수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
):
    """
    관리자 전용(admin_observability 읽기 이상):
    현재 필터 조건에 부합하는 감사로그를 엑셀 호환 UTF-8 BOM CSV 포맷으로 스트리밍 다운로드합니다.
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

    logs = q.order_by(AuditLog.created_at.desc()).limit(limit).all()

    # 엑셀 한글 깨짐 방지 UTF-8 BOM (\ufeff)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # 헤더 작성
    writer.writerow([
        "ID",
        "발생일시",
        "앱 식별자",
        "로그 유형",
        "심각도",
        "행위(Action)",
        "작업 수행자",
        "IP 주소",
        "제목",
        "상세 메시지",
        "리소스 유형",
        "리소스 ID"
    ])

    for item in logs:
        writer.writerow([
            item.id,
            item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
            item.app_id or "",
            item.log_type or "",
            item.severity or "",
            item.action or "",
            item.user_summary or (f"User #{item.user_id}" if item.user_id else "SYSTEM"),
            item.ip_address or "",
            item.title or "",
            item.message or "",
            item.resource_type or "",
            item.resource_id or ""
        ])

    csv_data = output.getvalue()
    output.close()

    # 📜 [보안 감사로그]: 감사로그 CSV 내보내기 행위 자동 기록
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="SECURITY",
        severity="INFO",
        action="LOG_EXPORT_CSV",
        title=f"관리자({current_user.username})에 의한 감사로그 CSV 다운로드",
        user=current_user,
        resource_type="audit_log",
        message=f"감사로그 {len(logs)}건을 CSV로 내보내기 다운로드했습니다. (필터: app_id={app_id}, type={log_type}, query={query})",
        metadata={"count": len(logs), "app_id": app_id, "log_type": log_type, "query": query}
    )

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_suffix = log_type.lower() if log_type else "all"
    filename = f"audit_logs_{type_suffix}_{now_str}.csv"

    return StreamingResponse(
        io.BytesIO(csv_data.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get(
    "/system-logs/download",
    summary="서버 원시 시스템 콘솔 로그(.log) 다운로드"
)
def download_system_console_log(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read)
):
    """
    관리자 전용(admin_observability 읽기 이상):
    Uvicorn/FastAPI 런타임 콘솔 표준 출력이 누적된 system.log 파일을 다운로드합니다.
    """
    # test/logs/system.log 절대 경로 산출 (3단계 상위 logs 디렉토리)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    log_file_path = os.path.join(base_dir, "logs", "system.log")

    if not os.path.exists(log_file_path):
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] [system] System log file initialized.\n")

    # 📜 [보안 감사로그]: 시스템 콘솔 로그 다운로드 기록
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="SECURITY",
        severity="WARN",
        action="SYSTEM_LOG_DOWNLOAD",
        title=f"관리자({current_user.username})에 의한 시스템 콘솔 로그 파일 다운로드",
        user=current_user,
        resource_type="system_log",
        message="서버 런타임 원시 콘솔 로그 파일(system.log) 다운로드를 수행했습니다."
    )

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"system_console_{now_str}.log"

    # 🔒 [동시 쓰기 레이스 컨디션 방어]:
    # 실시간으로 계속 추가되는 로그 파일과의 Content-Length 불일치(502 Bad Gateway)를 원천 차단하기 위해
    # 현재 시점의 안전한 바이트 스냅샷을 메모리로 읽어 정확한 바이트 크기로 응답합니다.
    try:
        with open(log_file_path, "rb") as f:
            file_bytes = f.read()
    except Exception as e:
        logger.error(f"로그 파일 읽기 오류: {e}")
        file_bytes = f"로그 파일을 읽는 중 오류가 발생했습니다: {str(e)}".encode("utf-8")

    return Response(
        content=file_bytes,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_bytes))
        }
    )
