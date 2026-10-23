"""
============================================================================
[배차 관리 및 노선 마스터 모델 (models/dispatch.py)]
============================================================================

💡 이 파일의 역할:
제주 버스 운송의 핵심 도메인인 노선 마스터(RouteMaster), 상세 시간표(RouteTimetable),
그리고 일일 배차 스냅샷(Dispatch) 모델을 정의합니다.
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from models.base import Base


class RouteMaster(Base):
    """
    노선 마스터 모델 (버전 정보 및 정규/임시 형태 구분 수용)
    - 동일 노선명이라도 적용 기간(start_date ~ end_date)에 따라 독립된 버전(v1, v2...)이 생성됩니다.
    - route_type 컬럼을 통해 정규노선(REGULAR)과 임시노선(TEMPORARY)을 구분합니다.
    """
    __tablename__ = "route_master"

    id = Column(Integer, primary_key=True)
    route_name = Column(String(100), nullable=False)
    route_type = Column(String(50), default="REGULAR", nullable=False) # REGULAR: 정규노선, TEMPORARY: 임시노선
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=True, index=True)                # 종료일이 없으면(현재 진행형) NULL
    vehicle_count = Column(Integer, default=0, nullable=False)
    version = Column(String(50), nullable=False)
    is_regular_duty = Column(Boolean, default=False, nullable=False)  # 당연 근무 여부 (배차 편의용)

    timetables = relationship("RouteTimetable", back_populates="master", cascade="all, delete-orphan")


class RouteTimetable(Base):
    """
    노선 상세 시간표 모델
    - 특정 RouteMaster 버전에 100% 종속됩니다.
    - 회차별 운행 순번(seq), 출발/도착 시각 및 기종점 위치를 포함합니다.
    """
    __tablename__ = "route_timetable"

    id = Column(Integer, primary_key=True)
    route_master_id = Column(Integer, ForeignKey("route_master.id", ondelete="CASCADE"), nullable=False)
    route_name = Column(String(100), nullable=False)
    seq = Column(Integer, nullable=False)            # 운행 순번 (1회차, 2회차...)
    start_time = Column(String(10), nullable=False)  # HH:MM
    end_time = Column(String(10), nullable=False)    # HH:MM
    start_location = Column(String(100), nullable=False)
    end_location = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    start_garage = Column(String(10), nullable=True) # 차량 출발 전 차고지 (최대 10자)
    end_garage = Column(String(10), nullable=True)   # 차량 종료 후 차고지 (최대 10자)
    is_regular_duty = Column(Boolean, default=False, nullable=False)

    master = relationship("RouteMaster", back_populates="timetables")


class Dispatch(Base):
    """
    배차 시스템 최종 실행 모델
    - 날짜(target_date) + 시간표ID(timetable_id)의 조합으로 고유한 운행 슬롯을 보장합니다.
    - 기사명, 차량번호, 출발 시간을 단순 외래키 참조가 아닌 스냅샷(Hard-copy) 형태로 저장하여 과거 이력을 보전합니다.
    """
    __tablename__ = "dispatch"

    id = Column(Integer, primary_key=True)
    target_date = Column(Date, nullable=False, index=True)
    timetable_id = Column(Integer, ForeignKey("route_timetable.id", ondelete="CASCADE"), nullable=False)
    
    driver_name = Column(String(50), nullable=True)  # 배정 기사명 스냅샷
    vehicle_no = Column(String(50), nullable=True)   # 배정 차량번호 스냅샷
    start_time = Column(String(10), nullable=True)   # 운행 실제 출발 시각 스냅샷
    
    status = Column(String(50), default="DRAFT", nullable=False) # DRAFT, CONFIRMED
    memo = Column(Text, nullable=True)

    timetable = relationship("RouteTimetable")

    __table_args__ = (
        UniqueConstraint('target_date', 'timetable_id', name='uq_dispatch_date_timetable'),
    )
