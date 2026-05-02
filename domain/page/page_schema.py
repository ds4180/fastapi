from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, Any

class PageBase(BaseModel):
    slug: str
    title: str
    content: Optional[str] = None
    content_json: Any
    status: str = "DRAFT"
    is_active: bool = True
    min_rank: int = 0
    published_at: datetime
    expired_at: Optional[datetime] = None
    redirect_url: Optional[str] = None

    @field_validator('slug')
    @classmethod
    def slug_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('슬러그는 비어둘 수 없습니다.')
        return v

class PageCreate(PageBase):
    pass

class PageUpdate(PageBase):
    id: int
    slug: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    content_json: Optional[Any] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    min_rank: Optional[int] = None
    published_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    redirect_url: Optional[str] = None

class PageResponse(PageBase):
    id: int
    view_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PageSimpleResponse(BaseModel):
    id: int
    slug: str
    title: str
    content: Optional[str] = None      # [v1.0.5] 본문 추가
    content_json: Optional[Any] = None # [v1.0.5] 본문 JSON 추가
    status: str
    is_active: bool = True
    published_at: datetime

    class Config:
        from_attributes = True
