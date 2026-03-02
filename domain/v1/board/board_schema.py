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
    content_json: Any
    extra_data: Dict[str, Any]
    status: str
    view_count: int
    create_date: datetime
    user_name: Optional[str] = None # 작성자 이름 추가
    is_read: bool = False # 읽음 여부 (M2M)
    like_count: int = 0
    comment_count: int = 0

    class Config:
        from_attributes = True

class PostListSchema(BaseModel):
    total: int = 0
    posts: List[PostSimpleSchema] = []
    board: BoardConfigSchema

class LandingPageResponse(BaseModel):
    config: Optional[BoardConfigSchema] = None
    post: Optional[PostSimpleSchema] = None
    message: str = "success"
