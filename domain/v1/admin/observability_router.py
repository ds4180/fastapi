"""
============================================================================
[통합 시스템 관제 및 감사로그 라우터 (domain/v1/admin/observability_router.py)]
============================================================================
- 모든 집계·필터링·세션 동기화·CSV/콘솔로그 스냅샷·정책 저장 비즈니스 로직은
  observability_admin_service 및 observability_policy_service로 분리하고,
  본 라우터는 HTTP 입출력, AppRegistry('observability') 4단계 권한 인가 및 감사로그만 담당합니다.
"""

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import require_app_permission
from core.permission import ROOT_RANK, can_access_app, get_user_rank
from database import get_db
from domain.system.observability_admin_service import (
    export_audit_logs_csv_data,
    get_live_sessions_data,
    get_observability_summary_data,
    kick_live_session_by_id,
    query_audit_logs_data,
    read_system_console_log_snapshot,
)
from domain.system.observability_policy_service import (
    BUILTIN_MASK_FIELDS,
    get_observability_settings,
    update_observability_settings,
)
from domain.v1.admin.observability_schema import (
    AuditLogListRes,
    LiveSessionItemRes,
    ObservabilitySummaryRes,
)
from models import AppRegistry, User

router = APIRouter(prefix="/v1/admin/observability", tags=["Admin Observability"])

check_obs_read = require_app_permission("observability", action="read")
check_obs_write = require_app_permission("observability", action="write")


def _can_write_observability(user: User, db: Session) -> bool:
    if get_user_rank(user) == ROOT_RANK:
        return True
    app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "observability").first()
    if not app_meta:
        return get_user_rank(user) >= 4
    return can_access_app(user, app_meta, action="write")


# ==========================================================================
# ⚙️ 0. 통합 관제 정책 설정 조회 / 수정
# ==========================================================================


@router.get("/settings", summary="통합 관제·감시·보존·내보내기 정책 설정 조회")
def get_observability_settings_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    return {
        "settings": get_observability_settings(db),
        "builtin_mask_fields": BUILTIN_MASK_FIELDS,
        "permissions": {
            "can_write": _can_write_observability(current_user, db),
        },
    }


@router.put("/settings", summary="통합 관제·감시·보존·내보내기 정책 설정 저장")
def update_observability_settings_api(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_write),
):
    old_cfg, new_cfg = update_observability_settings(db, payload)
    diff_payload = [
        {"field": k, "from": old_cfg.get(k), "to": new_cfg.get(k)}
        for k in new_cfg
        if old_cfg.get(k) != new_cfg.get(k)
    ]
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="CHANGE",
        severity="INFO",
        action="OBSERVABILITY_SETTINGS_UPDATED",
        title=f"관리자({current_user.username})에 의한 통합 관제 정책 설정 변경",
        user=current_user,
        resource_type="system_config",
        resource_id="observability_settings",
        diff_payload=diff_payload,
        message=f"통합 관제·감시·보존 정책 설정 {len(diff_payload)}개 항목을 갱신했습니다.",
    )
    return {
        "message": "통합 관제 정책 설정이 저장되었습니다.",
        "settings": new_cfg,
    }


# ==========================================================================
# 🌐 1. 실시간 활성 세션 관제
# ==========================================================================


@router.get(
    "/sessions",
    response_model=List[LiveSessionItemRes],
    summary="실시간 활성 세션 및 접속 이력 목록 조회",
)
def get_live_sessions(
    include_history: bool = Query(False, description="과거 만료/종료된 세션 접속 이력까지 전체 포함 여부"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="최대 조회 건수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    return get_live_sessions_data(db, include_history=include_history, limit=limit)


@router.post(
    "/sessions/kick/{target_session_id}",
    summary="특정 세션 강제 추방 (원클릭 KICK)",
)
def kick_session(
    target_session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_write),
):
    result = kick_live_session_by_id(db, target_session_id=target_session_id)
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="SECURITY",
        severity="WARN",
        action="SESSION_KICKED",
        title=f"관리자({current_user.username})에 의한 세션 #{result.id} 강제 추방",
        user=current_user,
        resource_type="user_session",
        resource_id=str(result.id),
        message=f"관리자 {current_user.username}(ID: {current_user.id})가 세션 #{result.id}을(를) 강제 종료시켰습니다.",
        metadata={"admin_id": current_user.id, "target_session_id": result.id, "session_key": result.session_key},
    )
    return {"message": "Success", "target_session_id": result.id}


# ==========================================================================
# 📊 2. 통합 감사로그 조회 & 통계 요약
# ==========================================================================


@router.get(
    "/summary",
    response_model=ObservabilitySummaryRes,
    summary="관제탑 실시간 요약 통계 조회",
)
def get_observability_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    return get_observability_summary_data(db)


@router.get(
    "/logs",
    response_model=AuditLogListRes,
    summary="전사 통합 감사로그 페이징 및 필터 검색",
)
def get_audit_logs(
    app_id: Optional[str] = Query(None, description="앱 식별자 필터"),
    log_type: Optional[str] = Query(None, description="'ACCESS' | 'CHANGE' | 'ERROR' | 'SECURITY'"),
    severity: Optional[str] = Query(None, description="'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'"),
    user_id: Optional[int] = Query(None, description="특정 사용자 user_id 필터"),
    query: Optional[str] = Query(None, description="제목, 내용, 사용자 스냅샷, 행위 검색어"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="페이지당 건수 (최대 100)"),
    skip: Optional[int] = Query(None, description="레거시 skip 파라미터 호환"),
    limit: Optional[int] = Query(None, description="레거시 limit 파라미터 호환"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    return query_audit_logs_data(
        db=db,
        app_id=app_id,
        log_type=log_type,
        severity=severity,
        user_id=user_id,
        query=query,
        page=page,
        page_size=page_size,
        skip=skip,
        limit=limit,
    )


# ==========================================================================
# 📥 3. 전사 감사로그 CSV 내보내기 & 시스템 원시 로그 다운로드
# ==========================================================================


@router.get(
    "/logs/export",
    summary="전사 감사로그 CSV 내보내기 다운로드",
)
def export_audit_logs_csv(
    app_id: Optional[str] = Query(None, description="앱 식별자 필터"),
    log_type: Optional[str] = Query(None, description="'ACCESS' | 'CHANGE' | 'ERROR' | 'SECURITY'"),
    severity: Optional[str] = Query(None, description="'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'"),
    user_id: Optional[int] = Query(None, description="특정 사용자 user_id 필터"),
    query: Optional[str] = Query(None, description="검색어"),
    limit: Optional[int] = Query(None, ge=1, le=50000, description="내보낼 최대 건수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    csv_bytes, count, filename = export_audit_logs_csv_data(
        db=db,
        app_id=app_id,
        log_type=log_type,
        severity=severity,
        user_id=user_id,
        query=query,
        limit=limit,
    )
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="SECURITY",
        severity="INFO",
        action="LOG_EXPORT_CSV",
        title=f"관리자({current_user.username})에 의한 감사로그 CSV 다운로드",
        user=current_user,
        resource_type="audit_log",
        message=f"감사로그 {count}건을 CSV로 내보내기 다운로드했습니다. (필터: app_id={app_id}, type={log_type}, query={query})",
        metadata={"admin_id": current_user.id, "count": count, "app_id": app_id, "log_type": log_type, "query": query},
    )
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/system-logs/download",
    summary="서버 원시 시스템 콘솔 로그(.log) 다운로드",
)
def download_system_console_log(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_obs_read),
):
    file_bytes, filename, truncated = read_system_console_log_snapshot(db)
    safe_log_audit(
        db=db,
        app_id="observability",
        log_type="SECURITY",
        severity="WARN",
        action="SYSTEM_LOG_DOWNLOAD",
        title=f"관리자({current_user.username})에 의한 시스템 콘솔 로그 파일 다운로드",
        user=current_user,
        resource_type="system_log",
        message=f"서버 런타임 원시 콘솔 로그 파일(system.log) 다운로드를 수행했습니다. (용량절삭={truncated})",
        metadata={"admin_id": current_user.id, "bytes": len(file_bytes), "truncated": truncated},
    )
    return Response(
        content=file_bytes,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )
