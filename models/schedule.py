"""
============================================================================
[일정 관리 모델 (models/schedule.py)]
============================================================================

💡 역할:
- 개인 일정(PERSONAL/ATTENDANCE), 사무실 일정(OFFICE), 전사 공지/공휴일(GLOBAL/HOLIDAY)
- 반복 규칙(JSONB: freq, interval, byDay, byMonthDay, until, count) 및 D-Day 지원
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from models.base import Base, JSONType


class Schedule(Base):
    """통합 일정 모델"""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    category = Column(String(30), nullable=False, default="PERSONAL", index=True)
    scope = Column(String(20), nullable=False, default="PERSONAL", index=True)
    color = Column(String(20), nullable=False, default="#3b82f6")

    start_at = Column(DateTime, nullable=False, index=True)
    end_at = Column(DateTime, nullable=True, index=True)
    is_all_day = Column(Boolean, default=False, nullable=False)

    display_mode = Column(String(20), default="bar", nullable=False)  # bar | background
    importance = Column(Integer, default=1, nullable=False)
    is_dday = Column(Boolean, default=False, nullable=False)
    recurrence_rule = Column(JSONType, default=dict, nullable=False)

    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    user = relationship("User")
