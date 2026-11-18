from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from domain.user.user_schema import User

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    parent_id: Optional[int] = None
    media_ids: Optional[List[int]] = []

class CommentUpdate(CommentBase):
    media_ids: Optional[List[int]] = None
    remove_media_ids: Optional[List[int]] = None

class Comment(CommentBase):
    id: int
    post_id: int
    user_id: int
    parent_id: Optional[int] = None
    create_date: datetime
    modify_date: Optional[datetime] = None
    user: Optional[User] = None
    sub_comments: List['Comment'] = []
    attachments: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)
