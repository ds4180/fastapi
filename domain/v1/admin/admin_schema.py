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
    description: Optional[str] = None
    frontend_route: Optional[str] = None
    main_component: Optional[str] = None
    api_module: Optional[str] = None
    admin_page: Optional[str] = None
    config_schema: Dict[str, Any] = {}
    min_rank: int = 1
    is_active: bool = True

class AppRegistryCreate(AppRegistryBase):
    pass

class AppRegistryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    frontend_route: Optional[str] = None
    main_component: Optional[str] = None
    api_module: Optional[str] = None
    admin_page: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    min_rank: Optional[int] = None
    is_active: Optional[bool] = None

class AppRegistrySchema(AppRegistryBase):
    created_at: datetime
    updated_at: Optional[datetime] = None
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
