"""
============================================================================
[사내 전역 공지 및 팝업 알림 모델 (models/alert.py)]
============================================================================

💡 이 파일의 역할:
상단 토스트 및 중앙 모달 팝업으로 사용자들에게 즉각 노출되는
사내 전역 공지 알림(Alert) 테이블을 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from models.base import Base


class Alert(Base):
    """사내 실시간 공지/모달 알림 모델"""
    __tablename__ = "alert"

    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    level = Column(Integer, default=1)
    style = Column(String, default="info")       # info, warning, error, success
    position = Column(String, default="top")     # top(토스트), modal(중앙 팝업)
    route = Column(String, nullable=True)
    redirect_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    target_users = Column(String, nullable=True) # 특정 대상 유저 ID 목록 (쉼표 구분)
    confirm_text = Column(String, default="확인하였습니다")
    reset_sec = Column(Integer, default=0)
    create_date = Column(DateTime, nullable=False, default=datetime.now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", backref="created_alerts")
