from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

class BoardConfigSchema(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    layout_type: str
    items_per_page: int
    fields_def: List[Any]
    options: Dict[str, Any]
    perm_read: Dict[str, Any]
    perm_write: Dict[str, Any]
    is_active: bool
    create_date: datetime

    class Config:
        from_attributes = True

class PostSimpleSchema(BaseModel):
    id: int
    title: str
    content: Optional[str] = None # HTML 본문 추가
    content_json: Optional[Any] = None
    extra_data: Dict[str, Any] = {} # 커스텀 필드 데이터
    status: str
    view_count: int
    create_date: datetime
    user_name: Optional[str] = None
    is_read: bool = False
    like_count: int = 0
    comment_count: int = 0

    class Config:
        from_attributes = True

# --- Post CRUD Schemas ---

class PostCreate(BaseModel):
    title: str
    content: Optional[str] = None
    content_json: Optional[Any] = None
    extra_data: Dict[str, Any] = {}
    status: str = "published"

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_json: Optional[Any] = None
    extra_data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class PostListSchema(BaseModel):
    total: int = 0
    posts: List[PostSimpleSchema] = []
    board: BoardConfigSchema

class LandingPageResponse(BaseModel):
    config: Optional[BoardConfigSchema] = None
    post: Optional[PostSimpleSchema] = None
    message: str = "success"
