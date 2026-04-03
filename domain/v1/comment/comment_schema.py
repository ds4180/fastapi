from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from domain.user.user_schema import User

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    parent_id: Optional[int] = None

class CommentUpdate(CommentBase):
    pass

class Comment(CommentBase):
    id: int
    post_id: int
    user_id: int
    parent_id: Optional[int] = None
    create_date: datetime
    modify_date: Optional[datetime] = None
    user: Optional[User] = None
    sub_comments: List['Comment'] = []

    model_config = ConfigDict(from_attributes=True)
