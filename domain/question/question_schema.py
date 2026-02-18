import datetime

from pydantic import BaseModel, field_validator

from domain.answer.answer_schema import Answer
from domain.user.user_schema import User




class QuestionImage(BaseModel):
    id: int
    filename: str
    original_name: str
    thumbnail_filename: str | None = None
    question_id: int

    class Config:
        from_attributes = True


class Question(BaseModel):

    id: int
    subject: str
    content: str
    create_date: datetime.datetime
    answers: list[Answer]=[]
    user: User | None
    is_read: bool = False
    read_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    soso_count: int = 0
    my_reaction: str | None = None
    images: list[QuestionImage] = []

    class Config:
        from_attributes = True

class QuestionList(BaseModel):
    total: int = 0
    question_list: list[Question] = []


class QuestionCreate(BaseModel):
    subject: str
    content: str
    image_files: list[dict] = [] # [{'filename': '...', 'original_name': '...'}]

    @field_validator('subject', 'content')
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('빈 값은 허용되지 않습니다.')
        return v
    

class QuestionUpdate(QuestionCreate):
    question_id: int
    image_files: list[dict] = [] # [{'filename': '...', 'original_name': '...'}]


class QuestionDelete(BaseModel):
    question_id: int

class QuestionReactionCreate(BaseModel):
    question_id: int
    reaction_type: str # 'like', 'dislike', 'soso'