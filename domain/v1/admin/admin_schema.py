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
