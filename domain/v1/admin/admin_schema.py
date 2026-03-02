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
