"""
============================================================================
[휴무 및 결근 신청 모델 (models/dayoff.py)]
============================================================================

💡 이 파일의 역할:
기사님 및 직원들의 휴무 신청(DayOff), 결재 상태(REQUESTED, APPROVED 등),
및 일자별 중복 신청 방지 인덱스를 관리합니다.
"""

from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, Boolean, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from models.base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class DayOff(Base):
    """휴무 및 연차 신청 모델"""
    __tablename__ = "dayoff"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String, nullable=False) # 휴무 종류
    status = Column(String, default="REQUESTED") # REQUESTED, APPROVED, REJECTED
    memo = Column(Text, nullable=True)
    
    group_id = Column(String, nullable=True, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)
    create_date = Column(DateTime, nullable=False, default=datetime.now)

    # 동일 사용자가 동일 날짜에 중복 신청하는 것을 방지하는 부분 인덱스
    __table_args__ = (
        Index('ix_dayoff_user_date_active', 'user_id', 'date', 
              unique=True, postgresql_where=(is_deleted == False)),
    )

    user = relationship("User", back_populates="dayoffs")


class DayOffPolicy(Base):
    """결근/휴무 정책 및 정원 Append-Only 이력 테이블"""
    __tablename__ = "dayoff_policy"

    id = Column(Integer, primary_key=True)
    effective_date = Column(Date, nullable=False, default=date.today, index=True)
    classify_mode = Column(String(20), nullable=False, default="BOTH")
    fcfs_groups = Column(JSONType, nullable=False, default=list)
    fcfs_ranks = Column(JSONType, nullable=False, default=list)
    daily_quota = Column(Integer, nullable=False, default=3)
    date_overrides = Column(JSONType, nullable=False, default=dict)
    max_monthly_count = Column(Integer, nullable=False, default=0)
    max_days_per_request = Column(Integer, nullable=False, default=0)
    min_advance_days = Column(Integer, nullable=False, default=0)
    max_advance_days = Column(Integer, nullable=False, default=0)
    etc = Column(JSONType, nullable=False, default=dict)
    is_deleted = Column(Boolean, default=False, nullable=False)
    create_date = Column(DateTime, nullable=False, default=datetime.now)
