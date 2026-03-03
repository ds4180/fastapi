from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Dict
from datetime import datetime, date

# --- 메뉴 스키마 (기존 유지) ---
class MenuBase(BaseModel):
    title: str
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: str = "URL"
    external_url: Optional[str] = None
    order: int = 0
    is_visible: bool = True
    min_rank: int = 0
    board_id: Optional[int] = None
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
    board_id: Optional[int] = None
    page_id: Optional[int] = None

class MenuSchema(MenuBase):
    id: int
    parent_id: Optional[int] = None
    sub_menus: List['MenuSchema'] = []
    class Config:
        from_attributes = True

# --- 유저 관리 스키마 (기존 유지) ---
class UserProfileSchema(BaseModel):
    rank_level: int
    is_active: bool
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

# --- BoardConfig 베이스 스키마 (fields_def 포함) ---
class BoardConfigBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    layout_type: str = "list"
    items_per_page: int = 10
    fields_def: List[Any] = [] # <--- 여기에 fields_def가 정의됨
    options: Dict[str, Any] = {}
    is_active: bool = True # Base에 추가

# --- BoardConfig 생성/수정/조회 스키마 ---
class BoardConfigCreate(BoardConfigBase): # Base 상속
    pass

class BoardConfigUpdate(BaseModel): # 일부 필드만 Optional로 업데이트
    slug: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    layout_type: Optional[str] = None
    items_per_page: Optional[int] = None
    fields_def: Optional[List[Any]] = None # <--- 여기에 fields_def 포함
    options: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class BoardConfigAdminSchema(BoardConfigBase): # Base 상속
    id: int
    create_date: datetime
    class Config:
        from_attributes = True
