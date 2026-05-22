from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Dict
from datetime import datetime, date

# --- 메뉴 스키마 ---
class MenuBase(BaseModel):
    title: str
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: str = "URL" # URL, APP, PAGE, DIVIDER
    external_url: Optional[str] = None
    order: int = 0
    is_visible: bool = True
    min_rank: int = 0
    app_id: Optional[str] = None
    app_instance_id: Optional[int] = None
    page_id: Optional[int] = None

class MenuCreate(MenuBase):
    parent_id: Optional[int] = None
    app_instance_id: Optional[Any] = None

class MenuUpdate(BaseModel):
    parent_id: Optional[int] = None
    title: Optional[str] = None
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: Optional[str] = None
    external_url: Optional[str] = None
    order: Optional[int] = None
    is_visible: Optional[bool] = None
    min_rank: Optional[int] = None
    app_id: Optional[str] = None
    app_instance_id: Optional[Any] = None
    page_id: Optional[int] = None

from typing import List, Optional, Any, Dict, Union

# ... (기존 코드 상단 생략)

class MenuSchema(MenuBase):
    id: int
    parent_id: Optional[int] = None
    app_instance_id: Optional[Union[int, str]] = None
    sub_menus: List['MenuSchema'] = []
    class Config:
        from_attributes = True

# --- 유저 관리 스키마 ---
class UserProfileSchema(BaseModel):
    rank_level: int = 0
    is_active: bool = True
    employee_no: Optional[str] = None
    joined_date: Optional[date] = None

    class Config:
        from_attributes = True

class UserAdminSchema(BaseModel):
    id: int
    username: str
    email: EmailStr
    real_name: Optional[str] = None
    profile: Optional[UserProfileSchema] = None

    class Config:
        from_attributes = True

class UserRankUpdate(BaseModel):
    rank_level: int

# --- System Config 스키마 ---
class SystemConfigSchema(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    updated_date: Optional[datetime] = None

    class Config:
        from_attributes = True

class SystemConfigUpdate(BaseModel):
    value: Any
    description: Optional[str] = None

# --- 시스템 App 관리 스키마 ---

class AppRegistryBase(BaseModel):
    app_id: str
    name: str
    title: Optional[str] = None                     # UI 표시 공식 명칭
    description: Optional[str] = None
    app_type: str = "INSTANCE"                      # INSTANCE | STATIC | SYSTEM
    frontend_route: Optional[str] = None            # Svelte 라우트 경로
    main_component: Optional[str] = None            # Dynamic Import용 컴포넌트명
    icon_default: Optional[str] = None              # 기본 아이콘
    # 보안 주권 설정
    min_read_rank: int = 0                          # 읽기/진입 최소 권한
    min_write_rank: int = 2                         # 쓰기/행위 최소 권한
    admin_ids: List[int] = []                       # 앱 자치 관리자 user_id 목록
    config_schema: Dict[str, Any] = {}              # 인스턴스별 설정 스키마
    is_active: bool = True

class AppRegistryCreate(AppRegistryBase):
    pass

class AppRegistryUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    app_type: Optional[str] = None
    frontend_route: Optional[str] = None
    main_component: Optional[str] = None
    icon_default: Optional[str] = None
    min_read_rank: Optional[int] = None
    min_write_rank: Optional[int] = None
    admin_ids: Optional[List[int]] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class AppRegistrySchema(AppRegistryBase):
    created_at: datetime
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# --- Service Registry 스키마 (서비스 대분류) ---

class ServiceRegistryBase(BaseModel):
    id: str          # 예: "comment", "upload", "reaction"
    name: str        # 표시 이름
    description: Optional[str] = None

class ServiceRegistryCreate(ServiceRegistryBase):
    pass

class ServiceRegistryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ServiceRegistrySchema(ServiceRegistryBase):
    class Config:
        from_attributes = True


# --- Service Engine 스키마 (실제 작동 엔진 버전) ---

class ServiceEngineBase(BaseModel):
    id: str                             # 예: "basic_comment_v1"
    registry_id: str                    # 속하는 ServiceRegistry.id
    version: str = "1.0.0"
    frontend_plugin: Optional[str] = None   # 렌더링할 Svelte 컴포넌트명
    config_schema: Dict[str, Any] = {}      # 엔진별 설정 스키마
    is_active: bool = True

class ServiceEngineCreate(ServiceEngineBase):
    pass

class ServiceEngineUpdate(BaseModel):
    version: Optional[str] = None
    frontend_plugin: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ServiceEngineSchema(ServiceEngineBase):
    created_at: datetime
    class Config:
        from_attributes = True


# --- Service App 스키마 (원자적 기능 단위) ---
class ServiceAppBase(BaseModel):
    name: str                           # 서비스 인스턴스 명칭
    engine_id: str                      # 기초가 되는 ServiceEngine.id
    config: Dict[str, Any] = {}         # 엔진 적용 설정
    is_active: bool = True

class ServiceAppCreate(ServiceAppBase):
    pass

class ServiceAppUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ServiceAppSchema(ServiceAppBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True


# --- Service Instance 스키마 (완성된 서비스 덩어리) ---
class ServiceInstanceBase(BaseModel):
    name: str                           # "자유게시판용 패키지" 등
    service_app_ids: Optional[List[int]] = [] # 조립될 서비스 앱 ID 리스트 (순서 중요)
    is_active: bool = True

class ServiceInstanceCreate(ServiceInstanceBase):
    pass

class ServiceInstanceUpdate(BaseModel):
    name: Optional[str] = None
    service_app_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

class ServiceInstanceSchema(ServiceInstanceBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True


# --- Frontend 전달용 Resolved Service Binding ---
class ResolvedServiceBinding(BaseModel):
    """프론트엔드 엔진에 전달할 최종 조립된 서비스 명세"""
    service_id: str                     # service_registry.id (e.g., "comment")
    engine_id: str                      # service_engine.id (e.g., "basic_comment_v1")
    service_component: str              # service_engine.frontend_plugin
    config: Dict[str, Any]              # ServiceApp.config

# --- 게시판/포스트 공통 스키마 ---
class BoardSimpleSchema(BaseModel):
    id: int
    name: str
    slug: str
    class Config: from_attributes = True

class PostSimpleAdminSchema(BaseModel):
    id: int
    title: str
    create_date: datetime
    class Config: from_attributes = True

# --- BoardConfig 베이스 스키마 ---
class BoardConfigBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    layout_type: str = "list"
    items_per_page: int = 10
    fields_def: List[Any] = []
    options: Dict[str, Any] = {}
    service_instance_id: Optional[int] = None # 서비스 번들 바인딩
    is_active: bool = True

class BoardConfigCreate(BoardConfigBase):
    pass

class BoardConfigUpdate(BaseModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    layout_type: Optional[str] = None
    items_per_page: Optional[int] = None
    fields_def: Optional[List[Any]] = None
    options: Optional[Dict[str, Any]] = None
    service_instance_id: Optional[int] = None
    is_active: Optional[bool] = None

class BoardConfigAdminSchema(BoardConfigBase):
    id: int
    create_date: datetime
    class Config:
        from_attributes = True

# --- System Task 스키마 ---
class SystemTaskBase(BaseModel):
    task_type: str
    payload: Dict[str, Any] = {}
    priority: int = 5
    unique_key: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    cron_expression: Optional[str] = None
    repeat_interval: Optional[int] = None
    max_retries: int = 3
    timeout_sec: int = 300
    tags: List[str] = []

class SystemTaskCreate(SystemTaskBase):
    pass

class SystemTaskSchema(SystemTaskBase):
    id: int
    status: str
    retry_count: int
    progress_pct: int
    error_log: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =====================================================================
# 🚐 [v3.0.0] 노선 마스터 및 시간표 관리용 Pydantic 스키마
# =====================================================================

class RouteTimetableBase(BaseModel):
    """
    상세 회차 시간표 기본 스키마
    - seq: 운행 순번 (1회차, 2회차...)
    - start_time / end_time: 출발/도착 HH:MM 시간 포맷
    - start_location / end_location: 시종점 상세 정보
    """
    seq: int
    start_time: str
    end_time: str
    start_location: str
    end_location: str
    start_garage: Optional[str] = None
    end_garage: Optional[str] = None
    is_regular_duty: bool = False

class RouteTimetableCreate(RouteTimetableBase):
    """상세 시간표 생성 요청 스키마"""
    pass

class RouteMasterCreate(BaseModel):
    """
    노선 마스터 정보 및 상세 시간표 일괄 생성 요청 스키마
    - route_name: 노선 대표명 (예: "100번")
    - route_type: "REGULAR" (정규) 또는 "TEMPORARY" (임시)
    - start_date / end_date: 해당 버전의 일자 기준 유효 시작/종료일
    - vehicle_count: 해당 버전에 할당된 총 배차 차량 대수
    - version: 버전 태그 (예: "v1", "v2", "2026-Summer")
    - timetables: 일괄 등록할 시간표 리스트
    """
    route_name: str
    route_type: str = "REGULAR"
    start_date: date
    end_date: Optional[date] = None
    vehicle_count: int = 0
    version: str
    is_regular_duty: bool = False
    timetables: List[RouteTimetableCreate] = []

class RouteMasterUpdate(BaseModel):
    """
    노선 마스터 정보 및 상세 시간표 일괄 수정 요청 스키마
    - 제공된 필드만 선택적으로 변경하며, timetables가 제공될 경우 기존 시간표를 모두 지우고 재생성(Cascade)합니다.
    """
    route_name: Optional[str] = None
    route_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    vehicle_count: Optional[int] = None
    version: Optional[str] = None
    is_regular_duty: Optional[bool] = None
    timetables: Optional[List[RouteTimetableCreate]] = None


# =====================================================================
# 🚐 [v3.0.0] 일일 배차 관리용 Pydantic 스키마
# =====================================================================

class DispatchRowResponse(BaseModel):
    """
    배차 조회 시 응답 데이터 스키마 (시간표 상세와 기배정 데이터를 결합)
    """
    id: Optional[int] = None
    timetable_id: int
    seq: int
    start_time: str
    end_time: str
    start_location: str
    end_location: str
    driver_name: Optional[str] = None
    tomorrow_driver_name: Optional[str] = None
    yesterday_driver_name: Optional[str] = None
    vehicle_no: Optional[str] = None
    status: str = "DRAFT"
    memo: Optional[str] = None
    is_regular_duty: bool = False
    is_tomorrow_regular_duty: bool = False
    is_yesterday_regular_duty: bool = False
    is_inherited: bool = False
    is_tomorrow_inherited: bool = False

    class Config:
        from_attributes = True

class DispatchRowInput(BaseModel):
    """
    배차 임시저장/확정 시 각 행별 운행 데이터 입력 스키마
    """
    timetable_id: int
    driver_name: Optional[str] = None
    tomorrow_driver_name: Optional[str] = None
    vehicle_no: Optional[str] = None
    start_time: Optional[str] = None
    memo: Optional[str] = None

class DispatchSavePayload(BaseModel):
    """
    일자별 특정 노선의 전체 배차 내역 저장/수정 요청 스키마
    """
    target_date: date
    route_master_id: int
    status: str = "DRAFT"  # DRAFT | CONFIRMED
    rows: List[DispatchRowInput] = []


