"""
============================================================================
[통합 관제·감사로그 비즈니스 서비스 (domain/system/observability_admin_service.py)]
============================================================================
- observability_router.py에 혼재되어 있던 세션 동기화·조회, 요약 통계 집계,
  감사로그 필터 검색, UTF-8 BOM CSV 스트림 생성, 시스템 콘솔 로그 안전 스냅샷(Tail 제한)
  로직을 서비스 계층으로 분리하고 동적 정책(observability_settings)을 강제 적용합니다.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.session import sync_expired_sessions
from domain.system.observability_policy_service import get_observability_settings
from domain.user import user_crud
from domain.v1.admin.observability_schema import (
    AuditLogListRes,
    LiveSessionItemRes,
    ObservabilitySummaryRes,
)
from models import AppRegistry, AuditLog, User, UserSession

logger = logging.getLogger("admin.observability")


def get_live_sessions_data(
    db: Session,
    include_history: bool = False,
    limit: Optional[int] = None,
) -> List[LiveSessionItemRes]:
    """Redis 자가치유 동기화 후 실시간 활성 세션(또는 과거 접속 이력 포함) 목록을 반환합니다."""
    settings = get_observability_settings(db)
    eff_limit = min(max(int(limit or settings.get("ui_session_history_limit", 100)), 1), 500)

    sync_expired_sessions(db)

    query = db.query(UserSession).join(User, UserSession.user_id == User.id)
    if not include_history:
        query = query.filter(UserSession.status == "ACTIVE")

    sessions = query.order_by(UserSession.last_activity.desc()).limit(eff_limit).all()

    items: List[LiveSessionItemRes] = []
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


def kick_live_session_by_id(db: Session, target_session_id: str) -> UserSession:
    """의심 세션을 ID 또는 session_key로 강제 만료(KICKED_OUT) 처리합니다."""
    result = user_crud.kick_session(db, session_id=target_session_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"세션 식별자 '{target_session_id}'을(를) 찾을 수 없습니다.",
        )
    return result


def get_observability_summary_data(db: Session) -> ObservabilitySummaryRes:
    """오늘 기준 실시간 관제 4대 지표 요약 및 동적 앱 필터 옵션 집계"""
    today_start = datetime.combine(date.today(), datetime.min.time())

    active_sessions = sync_expired_sessions(db)

    today_logins = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.log_type == "ACCESS",
            AuditLog.action == "LOGIN_SUCCESS",
            AuditLog.created_at >= today_start,
        )
        .scalar()
        or 0
    )
    today_changes = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.log_type == "CHANGE", AuditLog.created_at >= today_start)
        .scalar()
        or 0
    )
    today_errors = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.log_type == "ERROR", AuditLog.created_at >= today_start)
        .scalar()
        or 0
    )
    today_security = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.log_type == "SECURITY", AuditLog.created_at >= today_start)
        .scalar()
        or 0
    )
    today_error_alert = today_errors + today_security

    app_name_map: Dict[str, str] = {}
    for reg_id, reg_name in db.query(AppRegistry.app_id, AppRegistry.name).all():
        if reg_id:
            app_name_map[str(reg_id).strip()] = str(reg_name or reg_id).strip()
    for (log_app_id,) in db.query(AuditLog.app_id).distinct().all():
        if log_app_id:
            aid = str(log_app_id).strip()
            if aid and aid not in app_name_map:
                app_name_map[aid] = aid

    app_options = [{"id": aid, "name": app_name_map[aid]} for aid in sorted(app_name_map.keys())]

    return ObservabilitySummaryRes(
        active_sessions_count=active_sessions,
        today_logins_count=today_logins,
        today_changes_count=today_changes,
        today_errors_count=today_errors,
        today_security_count=today_security,
        active_sessions=active_sessions,
        today_access_count=today_logins,
        today_change_count=today_changes,
        today_error_alert_count=today_error_alert,
        app_options=app_options,
    )


def _apply_audit_log_filters(
    q,
    app_id: Optional[str] = None,
    log_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
):
    if app_id:
        q = q.filter(AuditLog.app_id == app_id)
    if log_type:
        q = q.filter(AuditLog.log_type == log_type.upper())
    if severity:
        q = q.filter(AuditLog.severity == severity.upper())
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        q = q.filter(
            or_(
                AuditLog.title.ilike(search_pattern),
                AuditLog.message.ilike(search_pattern),
                AuditLog.user_summary.ilike(search_pattern),
                AuditLog.action.ilike(search_pattern),
            )
        )
    return q


def query_audit_logs_data(
    db: Session,
    app_id: Optional[str] = None,
    log_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[int] = None,
    query: Optional[str] = None,
    page: int = 1,
    page_size: Optional[int] = None,
    skip: Optional[int] = None,
    limit: Optional[int] = None,
) -> AuditLogListRes:
    """필터·검색·페이징이 적용된 감사로그 목록과 요약 통계를 반환합니다."""
    settings = get_observability_settings(db)
    eff_page_size = min(max(int(page_size or settings.get("ui_log_page_size", 20)), 1), 100)

    q = _apply_audit_log_filters(
        db.query(AuditLog),
        app_id=app_id,
        log_type=log_type,
        severity=severity,
        user_id=user_id,
        search=query,
    )

    total = q.count()
    eff_offset = skip if skip is not None else ((max(1, page) - 1) * eff_page_size)
    eff_limit = min(max(int(limit), 1), 100) if limit is not None else eff_page_size

    items = q.order_by(AuditLog.created_at.desc()).offset(max(0, eff_offset)).limit(eff_limit).all()
    summary = get_observability_summary_data(db)

    return AuditLogListRes(
        items=items,
        total=total,
        page=max(1, page),
        page_size=eff_limit,
        summary=summary,
    )


def export_audit_logs_csv_data(
    db: Session,
    app_id: Optional[str] = None,
    log_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[int] = None,
    query: Optional[str] = None,
    limit: Optional[int] = None,
) -> Tuple[bytes, int, str]:
    """동적 정책(allow_csv_export, csv_export_max_rows)을 적용하여 UTF-8 BOM CSV 바이트를 생성합니다."""
    settings = get_observability_settings(db)
    if not settings.get("allow_csv_export", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="현재 관제 정책 설정에 의해 감사로그 CSV 내보내기가 비활성화되어 있습니다.",
        )

    max_rows = int(settings.get("csv_export_max_rows", 5000))
    eff_limit = min(max(int(limit or max_rows), 1), max_rows)

    q = _apply_audit_log_filters(
        db.query(AuditLog),
        app_id=app_id,
        log_type=log_type,
        severity=severity,
        user_id=user_id,
        search=query,
    )
    logs = q.order_by(AuditLog.created_at.desc()).limit(eff_limit).all()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
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
            "리소스 ID",
        ]
    )

    for item in logs:
        writer.writerow(
            [
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
                item.resource_id or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_suffix = log_type.lower() if log_type else "all"
    filename = f"audit_logs_{type_suffix}_{now_str}.csv"
    return csv_bytes, len(logs), filename


def read_system_console_log_snapshot(db: Session) -> Tuple[bytes, str, bool]:
    """
    동적 정책(allow_system_log_download, system_log_max_download_mb)을 적용하여
    서버 system.log의 안전한 바이트 스냅샷을 반환합니다.
    파일 크기가 상한을 초과할 경우 최신 Tail 구간만 메모리로 읽어 OOM 및 502를 방지합니다.
    """
    settings = get_observability_settings(db)
    if not settings.get("allow_system_log_download", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="현재 관제 정책 설정에 의해 서버 원시 콘솔 로그 다운로드가 비활성화되어 있습니다.",
        )

    max_mb = int(settings.get("system_log_max_download_mb", 10))
    max_bytes = max_mb * 1024 * 1024

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    log_file_path = os.path.join(base_dir, "logs", "system.log")

    if not os.path.exists(log_file_path):
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] [system] System log file initialized.\n"
            )

    truncated = False
    try:
        file_size = os.path.getsize(log_file_path)
        with open(log_file_path, "rb") as f:
            if file_size > max_bytes:
                f.seek(file_size - max_bytes)
                # 첫 불완전 라인 건너뛰기
                f.readline()
                tail_bytes = f.read()
                notice = (
                    f"[TRUNCATED BY POLICY] 파일 전체 크기({file_size / (1024 * 1024):.1f}MB)가 "
                    f"최대 다운로드 제한({max_mb}MB)을 초과하여 최신 Tail 구간만 포함했습니다.\n"
                ).encode("utf-8")
                file_bytes = notice + tail_bytes
                truncated = True
            else:
                file_bytes = f.read()
    except Exception as e:
        logger.error(f"로그 파일 읽기 오류: {e}")
        file_bytes = f"로그 파일을 읽는 중 오류가 발생했습니다: {str(e)}".encode("utf-8")

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"system_console_{now_str}.log"
    return file_bytes, filename, truncated
