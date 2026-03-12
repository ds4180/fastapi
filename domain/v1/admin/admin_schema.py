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

class MenuUpdate(BaseModel):
    title: Optional[str] = None
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: Optional[str] = None
    external_url: Optional[str] = None
    order: Optional[int] = None
    is_visible: Optional[bool] = None
    min_rank: Optional[int] = None
    app_id: Optional[str] = None
    app_instance_id: Optional[int] = None
    page_id: Optional[int] = None

class MenuSchema(MenuBase):
    id: int
    parent_id: Optional[int] = None
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


# --- Service Binding 스키마 (앱 인스턴스 ↔ 엔진 연결) ---

class ServiceBindingBase(BaseModel):
    target_app: str                         # "board", "dashboard" 등 app_id
    target_id: int                          # 앱 인스턴스 ID (board_id 등)
    engine_id: str                          # 연결할 ServiceEngine.id
    custom_config: Dict[str, Any] = {}      # 바인딩별 커스텀 설정
    min_write_rank: Optional[int] = None    # null이면 AppRegistry 설정 상속
    order: int = 0
    is_active: bool = True

class ServiceBindingCreate(ServiceBindingBase):
    pass

class ServiceBindingUpdate(BaseModel):
    custom_config: Optional[Dict[str, Any]] = None
    min_write_rank: Optional[int] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class ServiceBindingSchema(ServiceBindingBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

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
    is_active: Optional[bool] = None

class BoardConfigAdminSchema(BoardConfigBase):
    id: int
    create_date: datetime
    class Config:
        from_attributes = True
