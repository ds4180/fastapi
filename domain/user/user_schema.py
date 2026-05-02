from pydantic import BaseModel, field_validator, EmailStr
from pydantic_core.core_schema import FieldValidationInfo
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    username: str
    password1: str
    password2: str
    email: EmailStr

    @field_validator('username', 'password1', 'password2', 'email')
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('빈 값은 허용되지 않습니다.')
        return v

    @field_validator('password2')
    def passwords_match(cls, v, info: FieldValidationInfo):
        if 'password1' in info.data and v != info.data['password1']:
            raise ValueError('비밀번호가 일치하지 않습니다.')
        return v


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str

class TokenResponse(Token):
    refresh_token: str

class UserLogin(BaseModel):
    username: str
    password: str

class RefreshToken(BaseModel):
    refresh_token: str


class User(BaseModel):
    id: int
    username: str
    email: EmailStr # EmailStr로 타입 강화
    rank_level: int = 0 # UserProfile에서 가져올 것임

    class Config:
        from_attributes = True
        # UserProfile의 rank_level을 User 스키마의 rank_level로 매핑
        model_computed_fields = {
            'rank_level': (lambda user: user.rank() if user.profile else 0, False)
        }

class UserList(BaseModel):
    users: list[User]

class UserSessionResponse(BaseModel):
    id: int
    user_id: int
    username: str
    device_category: str
    status: str
    device_name: Optional[str] = None
    ip_address: Optional[str] = None
    login_at: datetime
    logout_at: Optional[datetime] = None
    last_activity: datetime

    class Config:
        from_attributes = True
