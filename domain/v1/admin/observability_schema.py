"""
============================================================================
[통합 시스템 관제 및 감사로그 스키마 (domain/v1/admin/observability_schema.py)]
============================================================================

💡 이 파일의 역할:
실시간 세션 감시, 접속 이력, 앱 데이터 변경(Diff), 에러/보안 침해 관제 데이터를 위한 Pydantic DTO를 정의합니다.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AuditLogItemRes(BaseModel):
    """감사로그 단일 항목 응답"""
    id: int
    app_id: Optional[str] = None
    log_type: str
    severity: str
    action: str
    user_id: Optional[int] = None
    user_summary: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    title: str
    message: Optional[str] = None
    diff_payload: List[Dict[str, Any]] = Field(default_factory=list)
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ObservabilitySummaryRes(BaseModel):
    """관제탑 상단 실시간 요약 통계"""
    active_sessions_count: int = 0
    today_logins_count: int = 0
    today_changes_count: int = 0
    today_errors_count: int = 0
    today_security_count: int = 0


class AuditLogListRes(BaseModel):
    """감사로그 페이징 목록 응답"""
    items: List[AuditLogItemRes]
    total: int
    page: int
    page_size: int
    summary: ObservabilitySummaryRes


class LiveSessionItemRes(BaseModel):
    """실시간 활성 세션 항목 응답 (기존 v1/admin/sessions 호환)"""
    id: int
    session_key: str
    user_id: int
    username: str
    device_category: str
    status: str
    device_name: Optional[str] = None
    ip_address: Optional[str] = None
    login_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    class Config:
        from_attributes = True
