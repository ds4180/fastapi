"""
============================================================================
[인증 및 사용자 코어 모델 (models/user.py)]
============================================================================

💡 이 파일의 역할:
사용자 계정(User), 상세 프로필(UserProfile), 멀티 디바이스 로그인 세션(UserSession)을 정의합니다.
외래키 관계(relationship)는 모두 문자열 지연 바인딩("Post", "Question" 등)을 사용하여
다른 도메인 파일들과의 순환 참조(Circular Import)를 100% 원천 차단합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
from models.base import Base


class User(Base):
    """
    시스템 전체 사용자 계정 메인 테이블
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    real_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # 🔗 문자열 지연 바인딩: 타 모델 파일을 직접 임포트하지 않아 순환 참조가 발생하지 않습니다.
    questions = relationship("Question", back_populates="user")
    answers = relationship("Answer", back_populates="user")
    dayoffs = relationship("DayOff", back_populates="user")
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    read_histories = relationship("PostRead", back_populates="user")

    def rank(self):
        """사용자 등급(권한 레벨 0~4) 반환"""
        return self.profile.rank_level if self.profile else 0

    @property
    def role(self):
        """역할 문자열 반환 (ROLE_GUEST, ROLE_ADMIN, ROLE_STAFF_L*)"""
        r = self.rank()
        if r == 0:
            return "ROLE_GUEST"
        if r == 4:
            return "ROLE_ADMIN"
        return f"ROLE_STAFF_L{r}"


class UserProfile(Base):
    """
    사용자 상세 인사/프로필 정보 (기사 정보, 계좌, 사번 등)
    """
    __tablename__ = "user_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    rank_level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    employee_no = Column(String, nullable=True)
    resident_no = Column(String, nullable=True)
    joined_date = Column(Date, nullable=True)
    bank_name = Column(String, nullable=True)
    account_no = Column(String, nullable=True)
    admin_memo = Column(Text, nullable=True)

    user = relationship("User", back_populates="profile")


class UserSession(Base):
    """
    멀티 디바이스 실시간 로그인 세션 테이블 (Redis JTI와 연동)
    """
    __tablename__ = "user_session"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_key = Column(String, unique=True, nullable=False, index=True)
    device_category = Column(String, nullable=False, index=True) # MOBILE, DESKTOP
    status = Column(String, default="ACTIVE", index=True)        # ACTIVE, EXPIRED, KICKED_OUT
    device_name = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    login_at = Column(DateTime, default=datetime.now, index=True)
    logout_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", backref="sessions")
