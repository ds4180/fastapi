from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

class MenuBase(BaseModel):
    title: str
    parent_id: Optional[int] = None
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: str = "BOARD"  # BOARD, PAGE, URL, DIVIDER
    board_id: Optional[int] = None
    page_id: Optional[int] = None
    external_url: Optional[str] = None
    order: int = 0
    is_visible: bool = True
    min_rank: int = 0

class MenuCreate(MenuBase):
    pass

class MenuUpdate(BaseModel):
    title: Optional[str] = None
    parent_id: Optional[int] = None
    icon_name: Optional[str] = None
    icon_color: Optional[str] = None
    link_type: Optional[str] = None
    board_id: Optional[int] = None
    page_id: Optional[int] = None
    external_url: Optional[str] = None
    order: Optional[int] = None
    is_visible: Optional[bool] = None
    min_rank: Optional[int] = None

class MenuSchema(MenuBase):
    id: int
    sub_menus: List['MenuSchema'] = []

    class Config:
        from_attributes = True

class BoardSimpleSchema(BaseModel):
    id: int
    slug: str
    name: str
    
    class Config:
        from_attributes = True

class PostSimpleAdminSchema(BaseModel):
    id: int
    title: str
    
    class Config:
        from_attributes = True

# --- BoardConfig Management ---

class BoardConfigBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    layout_type: str = "list"
    items_per_page: int = 10
    fields_def: List[Any] = []
    options: Dict[str, Any] = {}
    perm_read: Dict[str, Any] = {"ROLE_GUEST": "GLOBAL"}
    perm_write: Dict[str, Any] = {"ROLE_USER": "GLOBAL"}
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
    perm_read: Optional[Dict[str, Any]] = None
    perm_write: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class BoardConfigAdminSchema(BoardConfigBase):
    id: int
    create_date: datetime

    class Config:
        from_attributes = True
