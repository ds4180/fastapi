"""
============================================================================
[생체 인증 / WebAuthn Passkey 모델 (models/passkey.py)]
============================================================================
"""

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from models.base import Base, JSONType


class UserPasskey(Base):
    """사용자별 WebAuthn(Passkey) 공개키 자격 증명 테이블"""
    __tablename__ = "user_passkeys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(512), unique=True, nullable=False, index=True)
    public_key = Column(Text, nullable=False)
    sign_count = Column(Integer, nullable=False, default=0)
    device_name = Column(String(120), nullable=False, default="내 보안 기기")
    transports = Column(JSONType, nullable=False, default=list)
    aaguid = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class BiometricAuthLog(Base):
    """생체 인증 등록·검증·원격 공조 감사 이력 테이블"""
    __tablename__ = "biometric_auth_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(String(512), nullable=True)
    action = Column(String(30), nullable=False)  # REGISTER | VERIFY | COOP_APPROVE | COOP_REJECT | REVOKE
    status = Column(String(20), nullable=False)  # SUCCESS | FAILED | REJECTED
    device_name = Column(String(120), nullable=True)
    ip_address = Column(String(64), nullable=True)
    detail = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
