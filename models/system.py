"""
============================================================================
[시스템 메타 및 자율 신경계 모델 (models/system.py)]
============================================================================

💡 이 파일의 역할:
시스템 환경설정(SystemConfig), 앱 레지스트리(AppRegistry), 레고형 서비스 엔진(Service*),
동적 사이드바 메뉴(Menu), 백그라운드 비동기 작업 스케줄러(SystemTask)를 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base


class SystemConfig(Base):
    """시스템 전역 동적 설정 테이블 (JSONB 저장)"""
    __tablename__ = "system_config"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    description = Column(String, nullable=True)
    updated_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AppRegistry(Base):
    """시스템에 등록된 앱(플러그인) 목록 메타데이터"""
    __tablename__ = "app_registry"

    app_id = Column(String, primary_key=True, index=True) # 앱 고유 식별자 (예: 'board', 'dispatch')
    name = Column(String, nullable=False)                 # 앱 이름
    title = Column(String, nullable=True)                 # UI 표시용 공식 명칭
    description = Column(Text, nullable=True)             # 요약 설명
    
    app_type = Column(String, default="INSTANCE")         # INSTANCE, STATIC, SYSTEM
    frontend_route = Column(String, nullable=True)        # Svelte 라우트 경로
    main_component = Column(String, nullable=True)        # 메인 컴포넌트명 (동적 런처용)
    icon_default = Column(String, nullable=True)          # 기본 아이콘
    
    min_read_rank = Column(Integer, default=0)            # 4단계: 읽기 최소 권한 랭킹 (0~9)
    min_write_rank = Column(Integer, default=2)           # 4단계: 쓰기 최소 권한 랭킹 (0~9)
    allow_groups = Column(JSONB, nullable=False, default=list) # 3단계: 허용 그룹 목록 (주그룹/부그룹 소속 시 읽기·쓰기 모두 가능)
    deny_groups = Column(JSONB, nullable=False, default=list)  # 2단계: 차단 그룹 목록 (주그룹/부그룹 소속 시 읽기·쓰기 모두 차단)
    admin_ids = Column(JSONB, default=list)               # 자치 관리자 ID 리스트
    
    config_schema = Column(JSONB, default=dict)           # 설정 스키마
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ServiceRegistry(Base):
    """서비스 앱 대분류 (댓글, 추천, 업로드 등)"""
    __tablename__ = "service_registry"

    id = Column(String, primary_key=True) # "comment", "upload"
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)


class ServiceEngine(Base):
    """실제 작동하는 레고 엔진 (v1, v2 등)"""
    __tablename__ = "service_engine"

    id = Column(String, primary_key=True) # "basic_comment_v1"
    registry_id = Column(String, ForeignKey("service_registry.id"), nullable=False)
    version = Column(String, nullable=False, default="1.0.0")
    
    frontend_plugin = Column(String, nullable=True) # 렌더링할 Svelte 컴포넌트 경로
    config_schema = Column(JSONB, default=dict)     # 엔진별 필수 설정 스키마
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class ServiceApp(Base):
    """원자적 기능 단위 (댓글, 설문 등)"""
    __tablename__ = "service_app"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    engine_id = Column(String, ForeignKey("service_engine.id"), nullable=False)
    config = Column(JSONB, default=dict)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class ServiceInstance(Base):
    """조합된 서비스 앱 덩어리 (조립 설명서)"""
    __tablename__ = "service_instance"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    service_app_ids = Column(JSONB, default=list) # 조립될 서비스 앱 ID 리스트
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class Menu(Base):
    """동적 3분할 대시보드 사이드바 메뉴 트리 모델"""
    __tablename__ = "menu"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("menu.id"), nullable=True)
    title = Column(String, nullable=False)
    icon_name = Column(String, nullable=True)
    icon_color = Column(String, nullable=True)
    link_type = Column(String, default="URL") # URL, APP, PAGE, DIVIDER
    app_id = Column(String, ForeignKey("app_registry.app_id"), nullable=True)
    app_instance_id = Column(Integer, nullable=True)
    page_id = Column(Integer, nullable=True)
    external_url = Column(String, nullable=True)
    order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)
    min_rank = Column(Integer, default=0)
    allow_groups = Column(JSONB, nullable=False, default=list) # 메뉴 허용 그룹 목록
    deny_groups = Column(JSONB, nullable=False, default=list)  # 메뉴 차단 그룹 목록

    sub_menus = relationship(
        "Menu", 
        backref=backref("parent", remote_side=[id]), 
        cascade="all, delete-orphan", 
        order_by="Menu.order"
    )


class SystemTask(Base):
    """
    [시스템 자율 신경계] 지능형 범용 비동기 태스크 및 스케줄러 엔진 모델
    파일 처리, 메일 발송, 예약 게시 등 비동기 백그라운드 작업을 관리합니다.
    """
    __tablename__ = "system_tasks"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(50), nullable=False, index=True) # 작업 종류 (예: 'MEDIA_GC', 'MAIL_SEND')
    payload = Column(JSONB, default=dict)                      # 작업 입력 데이터
    result = Column(JSONB, default=dict)                       # 작업 결과물

    priority = Column(Integer, default=5, index=True)          # 우선순위 (1: 매우급함, 10: 여유있음)
    unique_key = Column(String(100), unique=True)              # 중복 작업 방지 키
    parent_id = Column(Integer, ForeignKey("system_tasks.id")) # 연쇄 작업 부모 ID
    on_parent_failure = Column(String(20), default="CANCEL")   # 부모 실패 시 정책
    
    scheduled_at = Column(DateTime, default=datetime.now, index=True) # 실행 예정 시각
    cron_expression = Column(String(50), nullable=True)        # 반복 Cron 표현식
    repeat_interval = Column(Integer, nullable=True)          # 반복 주기 (초)
    
    status = Column(String(20), default="PENDING", index=True) # PENDING, RUNNING, SUCCESS, FAILED
    worker_id = Column(String(50), nullable=True)              # 작업자 워커 식별자
    progress_pct = Column(Integer, default=0)                  # 진행률 (0~100)
    
    retry_count = Column(Integer, default=0)                   # 재시도 횟수
    max_retries = Column(Integer, default=3)                   # 최대 재시도 한도
    expires_at = Column(DateTime, nullable=True)               # 만료 시각
    timeout_sec = Column(Integer, default=300)                 # 타임아웃 제한 (초)
    error_log = Column(Text, nullable=True)                    # 에러 로그
    tags = Column(JSONB, default=list)                         # 검색용 태그
    
    created_by = Column(Integer, ForeignKey("users.id"))       # 작업 생성자
    correlation_id = Column(String(100), index=True)           # 요청 추적 ID
    
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    parent = relationship("SystemTask", remote_side=[id], backref="children")
