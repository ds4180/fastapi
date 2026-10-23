"""
============================================================================
[휴무 및 결근 신청 모델 (models/dayoff.py)]
============================================================================

💡 이 파일의 역할:
기사님 및 직원들의 휴무 신청(DayOff), 결재 상태(REQUESTED, APPROVED 등),
및 일자별 중복 신청 방지 인덱스를 관리합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, Boolean, Index
from sqlalchemy.orm import relationship
from models.base import Base


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
