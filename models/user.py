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
from typing import Optional, List, Set
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base

# 🌐 크로스 DB 호환 (운영: PostgreSQL JSONB, 테스트: SQLite JSON)
JSONType = JSON().with_variant(JSONB, "postgresql")


class Group(Base):
    """
    [코어 그룹 마스터 테이블 (groups)]
    
    💡 정책재정의.md 반영:
    - 오직 root(rank_level == 9)만이 그룹 관리 페이지에서 생성·삭제·설정할 수 있는 공식 그룹 명부입니다.
    - 사용자는 여기에 등록된 그룹 코드(code)를 주그룹(1개) 또는 부그룹(1개 이상)으로 부여받습니다.
    - group_type: 'PRIMARY'(주그룹/본소속) | 'SECONDARY'(부그룹/직무·특권·제재)
    - category: 'GENERAL'(일반) | 'PRIVILEGE'(특권/Allow용) | 'RESTRICTION'(제재/Deny용)
    """
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # 그룹 고유 식별 코드 (예: '운수팀', '배차담당')
    name = Column(String(100), nullable=False)                          # 화면 표시용 그룹 이름
    group_type = Column(String(20), nullable=False, default="PRIMARY")  # PRIMARY, SECONDARY
    category = Column(String(20), nullable=False, default="GENERAL")    # GENERAL, PRIVILEGE, RESTRICTION
    description = Column(Text, nullable=True)                           # 그룹 설명 및 용도
    created_at = Column(DateTime, default=datetime.now, nullable=False)


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

    def rank(self) -> int:
        """
        사용자 권한 랭킹(0~9) 반환 (기본값: 0)
        - 0: GUEST, 1~8: 일반~관리자, 9: ROOT (시스템 절대 권한)
        """
        return self.profile.rank_level if self.profile and self.profile.rank_level is not None else 0

    def is_root(self) -> bool:
        """1단계 검증용: 사용자가 root(랭킹 9)인지 여부 반환"""
        return self.rank() == 9

    @property
    def primary_group(self) -> Optional[str]:
        """사용자의 주그룹(최대 1개, 없을 수 있음) 반환"""
        return self.profile.primary_group if self.profile else None

    @property
    def secondary_groups(self) -> List[str]:
        """사용자의 부그룹 리스트(1개 이상 복수 가능, 없을 수 있음) 반환"""
        if self.profile and isinstance(self.profile.secondary_groups, list):
            return self.profile.secondary_groups
        return []

    def all_groups(self) -> Set[str]:
        """
        2단계(deny) 및 3단계(allow) 고속 검사를 위해
        사용자의 주그룹(1개)과 부그룹(N개)을 합친 집합(Set)을 반환합니다.
        """
        groups: Set[str] = set()
        if self.primary_group:
            groups.add(self.primary_group)
        for g in self.secondary_groups:
            if g:
                groups.add(g)
        return groups

    @property
    def role(self) -> str:
        """역할 문자열 반환 (ROLE_GUEST, ROLE_ROOT, ROLE_ADMIN, ROLE_STAFF_L*)"""
        r = self.rank()
        if r == 0:
            return "ROLE_GUEST"
        if r == 9:
            return "ROLE_ROOT"
        if r == 4:
            return "ROLE_ADMIN"
        return f"ROLE_STAFF_L{r}"


class UserProfile(Base):
    """
    사용자 상세 권한/그룹 및 인사 프로필 정보
    
    💡 정책재정의.md 반영:
    - rank_level: 권한 랭킹 (0~9, 필수 기본값 0)
    - primary_group: 주그룹 (선택 사항, 1개만 선택 가능)
    - secondary_groups: 부그룹 (선택 사항, 1개 이상 복수 선택 가능 JSONB 리스트)
    """
    __tablename__ = "user_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    rank_level = Column(Integer, default=0, nullable=False)
    primary_group = Column(String(50), nullable=True, default=None)
    secondary_groups = Column(JSONType, nullable=False, default=list)
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
