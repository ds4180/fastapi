"""
============================================================================
[통합 감사로그 및 관제 모델 (models/audit.py)]
============================================================================

💡 이 파일의 역할:
시스템 내 모든 중요 활동(접속/인증, 앱 데이터 변경, 에러, 보안 침해)을 
불변(Append-Only)으로 영구 보존하는 전사 통합 감사로그 테이블(audit_logs)을 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base

# 🌐 크로스 데이터베이스 호환: PostgreSQL에서는 고성능 바이너리 JSONB, 테스트 SQLite에서는 표준 JSON
JSONType = JSON().with_variant(JSONB, "postgresql")

# 🛡️ 개인정보보호 및 보안을 위한 민감 필드 마스킹 목록
SENSITIVE_FIELDS = {
    "password",
    "resident_no",
    "account_no",
    "secret",
    "token",
    "session_key",
    "credit_card",
}


class AuditLog(Base):
    """
    [전사 통합 감사로그 테이블 (audit_logs)]
    
    4대 로그 분류:
    - ACCESS   : 로그인, 로그아웃, 세션 만료, 중복 로그인 추방 (KICKED_OUT)
    - CHANGE   : 배차, 차량, 휴무, 게시판 등 도메인 데이터 등록/수정/삭제 (Diff-Patch 보존)
    - ERROR    : 404, 422, 500 내부 서버 장애 및 API 실패
    - SECURITY : 403 권한 침해 시도, root 초특권 관리자 작업, 세션 강제 추방
    """
    __tablename__ = "audit_logs"

    # 🔑 SQLite(테스트)에서는 Integer Primary Key여야 autoincrement 지원, 운영(PostgreSQL)에서는 BigInteger
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)

    # 📱 관련 앱 엔진 식별자 (예: 'dispatch', 'vehicle', 'board', 'auth', 'system')
    app_id = Column(String(50), nullable=True, index=True)

    # 🗂️ 4대 대분류 ('ACCESS' | 'CHANGE' | 'ERROR' | 'SECURITY')
    log_type = Column(String(20), nullable=False, index=True)

    # 🚨 심각도 등급 ('INFO' | 'WARN' | 'ERROR' | 'CRITICAL')
    severity = Column(String(20), nullable=False, default="INFO", index=True)

    # 🎯 세부 행위 (예: 'LOGIN_SUCCESS', 'UPDATE', 'ACCESS_DENIED', 'SESSION_KICKED')
    action = Column(String(50), nullable=False, index=True)

    # 👤 작업 수행자 정보 (퇴사 시 외래키 무효화 대신 SET NULL로 이력 영구 보존)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # 📸 스냅샷: 인사이동/퇴사 후에도 변경 당시의 직급·부서를 영구 증명 (예: "홍길동 (운수1팀/Lv.2)")
    user_summary = Column(String(100), nullable=True)

    # 📦 변경 대상 리소스 명칭 및 식별자 (예: resource_type='dispatch_entry', resource_id='42')
    resource_type = Column(String(50), nullable=True, index=True)
    resource_id = Column(String(50), nullable=True, index=True)

    # 📝 관제 화면 표시용 한 줄 요약 제목
    title = Column(String(255), nullable=False)

    # 💬 상세 설명 또는 에러 스택 트레이스
    message = Column(Text, nullable=True)

    # 🔍 필드 단위 수정 전/후 Diff-Patch (PostgreSQL JSONB / SQLite JSON)
    diff_payload = Column(JSONType, nullable=False, default=list)

    # 🌐 요청 컨텍스트 메타데이터 (URL, HTTP Method, Request-ID, User-Agent 등)
    metadata_payload = Column("metadata", JSONType, nullable=False, default=dict)

    # 💻 접속 클라이언트 IP (IPv4 / IPv6)
    ip_address = Column(String(45), nullable=True)

    # ⏱️ 발생 시각 (초/밀리초 타임스탬프)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # 🚀 고속 페이징 조회를 위한 복합 인덱스
    __table_args__ = (
        Index("ix_audit_logs_app_created", "app_id", "created_at"),
        Index("ix_audit_logs_type_created", "log_type", "created_at"),
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
    )
