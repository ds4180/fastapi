"""
============================================================================
[모바일 웹 푸시(Web Push) 구독 모델 (models/push.py)]
============================================================================

💡 이 파일의 역할:
브라우저/PWA 백그라운드 푸시 알림 전송을 위한 사용자 디바이스별
VAPID 엔드포인트(endpoint)와 암호화 키(auth, p256dh)를 관리합니다.
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from models.base import Base


class PushSubscription(Base):
    """웹 푸시 알림 디바이스 구독 정보 테이블"""
    __tablename__ = "push_subscription"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
