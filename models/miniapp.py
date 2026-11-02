"""
============================================================================
[전사 통합 미니앱 마이크로 텍스트 엔진 모델 (models/miniapp.py)]
============================================================================

💡 이 파일의 역할:
메모(MEMO), 알람(ALARM), 지시사항(INSTRUCTION), 메시징(MESSAGE), 전사알림(NOTIFICATION)을
별도의 여러 테이블로 나누지 않고, 발신자(Sender)와 수신자(Receiver)의 관계 및 상태(Status)를 
기반으로 단 하나의 통일된 DB 테이블(miniapp_items)에서 처리하는 통합 엔티티 모델입니다.
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey, Index, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from models.base import Base, TimestampMixin

# 🌐 크로스 DB 호환 (운영: PostgreSQL JSONB, 테스트: SQLite JSON)
JSONType = JSON().with_variant(JSONB, "postgresql")


class MiniappItem(Base, TimestampMixin):
    """
    [미니앱 통합 액션 아이템 테이블 (miniapp_items)]
    
    5대 분류 (category):
    - MEMO         : 내가 나에게 남긴 메모 (sender == receiver)
    - ALARM        : 특정 시각에 울리는 리마인더 (sender == receiver, target_time 설정)
    - INSTRUCTION  : 상사가 사원에게 내린 업무 지시 (sender != receiver, status: PENDING/ONGOING/COMPLETED)
    - MESSAGE      : 동료 간 주고받는 메시지 (sender != receiver)
    - NOTIFICATION : 시스템/관리자 전사 공지 (receiver_id is None)
    """
    __tablename__ = "miniapp_items"

    # 🔑 SQLite(테스트) Integer 및 PostgreSQL BigInteger 호환 Primary Key
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)

    # 👤 1. 발신자와 수신자
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    # 🗂️ 2. 분류 카테고리 ('MEMO' | 'ALARM' | 'INSTRUCTION' | 'MESSAGE' | 'NOTIFICATION')
    category = Column(String(20), nullable=False, default="MEMO", index=True)

    # 📝 3. 텍스트 본문 및 제목
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)

    # 🎯 4. 상태 관리
    # 'PENDING'(대기/미확인), 'ONGOING'(진행중), 'COMPLETED'(완료), 'READ'(읽음)
    status = Column(String(20), default="PENDING", nullable=False, index=True)

    # ⏰ 5. 알람 울림 시각 또는 업무 마감일
    target_time = Column(DateTime, nullable=True)

    # 🔗 6. 원클릭 바로가기 시스템 링크 (예: '/v1/dispatch')
    link = Column(String(255), nullable=True)

    # 📦 7. 추가 메타데이터 (JSONB)
    extra_payload = Column(JSONType, nullable=False, default=dict)

    # 👥 관계 매핑
    sender = relationship("User", foreign_keys=[sender_id], backref="sent_miniapps")
    receiver = relationship("User", foreign_keys=[receiver_id], backref="received_miniapps")
    reads = relationship("MiniappRead", back_populates="item", cascade="all, delete-orphan")


class MiniappRead(Base, TimestampMixin):
    """
    [미니앱 전사/다중 공지 개별 수신 확인 서명 테이블 (miniapp_reads)]
    
    💡 방안 B 아키텍처:
    - 전사 공지(receiver_id IS NULL)는 miniapp_items에 단 1건만 존재합니다.
    - 사원들이 각자 [확인 완료] 또는 [지시 확인]을 누르면 이 테이블에 1인당 1건의 확인 서명이 기록됩니다.
    - 이를 통해 원본 공지 데이터를 훼손하지 않고, 사원별 확인/미확인 상태를 완벽히 격리합니다.
    """
    __tablename__ = "miniapp_reads"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    item_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("miniapp_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    confirmed_at = Column(DateTime, default=datetime.now, nullable=False)
    status = Column(String(20), default="READ", nullable=False)  # 'READ', 'CONFIRMED', 'COMPLETED'

    item = relationship("MiniappItem", back_populates="reads")
    user = relationship("User", backref="miniapp_read_records")

    __table_args__ = (
        UniqueConstraint("item_id", "user_id", name="uq_miniapp_read_user"),
    )


# 🔍 사용자별 미확인/미결 건수 조회를 위한 복합 인덱스
Index("ix_miniapp_receiver_status", MiniappItem.receiver_id, MiniappItem.status)
Index("ix_miniapp_receiver_category", MiniappItem.receiver_id, MiniappItem.category)
