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

    class Config:
        from_attributes = True

class LandingPageResponse(BaseModel):
    config: Optional[BoardConfigSchema] = None
    post: Optional[PostSimpleSchema] = None
    message: str = "success"
