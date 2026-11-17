"""
============================================================================
[블랙박스 비디오 관리 모델 (models/blackbox.py)]
============================================================================

💡 이 파일의 역할:
- BlackboxDevice : 차량에 설치된 블랙박스 본체 스펙(제조사, 모델, 채널, led_count 등)
- BlackboxVideo  : 비디오(SD카드) 장부 및 현재 위치(OFFICE | VEHICLE), 2자리 육안 식별번호(display_num)
- BlackboxUsage  : 비디오 ↔ 차량 사용 기간 원장 (비디오/차량/날짜 양방향 역조회)
- BlackboxRequest: 운전기사 비디오 교체/확인 요청 및 처리 내역
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    and_,
)
from sqlalchemy.orm import relationship
from models.base import Base


class BlackboxDevice(Base):
    """차량별 블랙박스 본체 스펙 모델"""
    __tablename__ = "blackbox_devices"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_no = Column(String(50), nullable=False, index=True)
    manufacturer = Column(String(100), nullable=True)
    model_name = Column(String(100), nullable=True)
    channels = Column(String(30), nullable=True)        # 예: 2CH, 4CH, 8CH
    led_count = Column(Integer, nullable=False, default=0)
    serial_no = Column(String(100), nullable=True)
    installed_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="NORMAL")  # NORMAL | REPAIR | REPLACED
    notes = Column(Text, nullable=True)

    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index(
            "ix_blackbox_devices_vehicle_active",
            "vehicle_no",
            unique=True,
            postgresql_where=(is_deleted == False),
        ),
    )


class BlackboxVideo(Base):
    """블랙박스 비디오 장부 및 현재 위치 모델"""
    __tablename__ = "blackbox_videos"

    id = Column(Integer, primary_key=True, index=True)
    video_no = Column(String(50), nullable=False, index=True)      # 고유 관리번호 (예: BB-0001)
    display_num = Column(String(3), nullable=False, index=True)    # 육안 식별 번호 (0~999, 최대 3자리)
    manufacturer = Column(String(100), nullable=True)
    spec = Column(String(150), nullable=True)                      # 용량/등급 스펙 (예: 128GB MLC)
    serial_no = Column(String(100), nullable=True)
    purchase_date = Column(Date, nullable=True)
    disposal_date = Column(Date, nullable=True)

    # 현재 위치는 사무실(OFFICE) 또는 차량(VEHICLE) 2가지뿐
    location_type = Column(String(20), nullable=False, default="OFFICE", index=True)
    current_vehicle_no = Column(String(50), nullable=True, index=True)
    mounted_at = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    usages = relationship("BlackboxUsage", back_populates="video", order_by="BlackboxUsage.started_at.desc()")

    __table_args__ = (
        Index(
            "ix_blackbox_videos_video_no_active",
            "video_no",
            unique=True,
            postgresql_where=(is_deleted == False),
        ),
        Index(
            "ix_blackbox_videos_display_num_active",
            "display_num",
            unique=True,
            postgresql_where=and_(is_deleted == False, disposal_date.is_(None)),
        ),
    )


class BlackboxUsage(Base):
    """비디오 ↔ 차량 사용기간 이력 테이블 (역조회용)"""
    __tablename__ = "blackbox_usages"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("blackbox_videos.id", ondelete="CASCADE"), nullable=False, index=True)
    video_no = Column(String(50), nullable=False, index=True)
    display_num = Column(String(3), nullable=False)
    vehicle_no = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    ended_at = Column(DateTime, nullable=True, index=True)
    notes = Column(Text, nullable=True)

    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    video = relationship("BlackboxVideo", back_populates="usages")


class BlackboxRequest(Base):
    """운전기사 블랙박스 비디오 교체/확인 요청 모델"""
    __tablename__ = "blackbox_requests"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    requester_name = Column(String(100), nullable=False)
    vehicle_no = Column(String(50), nullable=False, index=True)

    current_video_id = Column(Integer, ForeignKey("blackbox_videos.id"), nullable=True)
    current_video_no = Column(String(50), nullable=True)
    current_display_num = Column(String(3), nullable=True)

    reason_type = Column(String(30), nullable=False, default="CHECK")  # ACCIDENT | COMPLAINT | MALFUNCTION | ROUTINE | CHECK | ETC
    reason_detail = Column(Text, nullable=True)
    incident_date = Column(DateTime, nullable=True)

    status = Column(String(20), nullable=False, default="PENDING", index=True)  # PENDING | COMPLETED | REJECTED
    replacement_video_id = Column(Integer, ForeignKey("blackbox_videos.id"), nullable=True)
    replacement_video_no = Column(String(50), nullable=True)
    replacement_display_num = Column(String(3), nullable=True)

    admin_note = Column(Text, nullable=True)
    processed_by = Column(String(100), nullable=True)
    processed_at = Column(DateTime, nullable=True)

    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
