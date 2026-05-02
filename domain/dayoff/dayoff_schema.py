from pydantic import BaseModel, field_validator
import datetime
from typing import List, Optional
from enum import Enum

class DayOffType(str, Enum):
    ANNUAL = "ANNUAL"       # 연차
    SPECIAL = "SPECIAL"     # 경조사
    SICK = "SICK"           # 병가
    OFFICIAL = "OFFICIAL"   # 공가

class DayOffStatus(str, Enum):
    REQUESTED = "REQUESTED" # 신청
    APPROVED = "APPROVED"   # 승인
    REJECTED = "REJECTED"   # 반려
    CANCELLED = "CANCELLED" # 취소

class DayOffCreate(BaseModel):
    type: DayOffType
    dates: List[datetime.date]
    memo: Optional[str] = None
    
    @field_validator('dates')
    def check_dates_not_empty(cls, v):
        if not v:
            raise ValueError('날짜를 선택해야 합니다.')
        return v

class DayOffResponse(BaseModel):
    id: int
    date: str # 날짜 또는 날짜 범위 문자열
    type: DayOffType
    status: DayOffStatus
    category: Optional[str] = None
    memo: Optional[str] = None
    group_id: Optional[str] = None
    create_date: datetime.datetime
    user_id: int
    
    class Config:
        from_attributes = True

class DayOffListResponse(BaseModel):
    total: int
    data: List[DayOffResponse]
