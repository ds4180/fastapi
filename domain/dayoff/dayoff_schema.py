from pydantic import BaseModel, field_validator
import datetime
from typing import List, Optional, Dict, Any
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
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_days: Optional[int] = None
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

class DayOffPolicySchema(BaseModel):
    effective_date: Optional[datetime.date] = None
    classify_mode: Optional[str] = None          # "GROUP" | "RANK" | "BOTH"
    fcfs_groups: Optional[List[str]] = None
    fcfs_ranks: Optional[List[int]] = None
    daily_quota: Optional[int] = None
    date_overrides: Optional[Dict[str, int]] = None
    max_monthly_count: Optional[int] = None      # 월별 최대 결근 신청 횟수 (0=제한 없음)
    max_days_per_request: Optional[int] = None   # 1회 신청 시 최대 일수 (0=제한 없음)
    min_advance_days: Optional[int] = None       # 최소 신청 가능일 (D+X일부터, 0=오늘 D+0부터)
    max_advance_days: Optional[int] = None       # 최대 신청 가능일 (D+Y일까지, 0=제한 없음)
    etc: Optional[Dict[str, Any]] = None         # 확장용 JSONB

class DayOffDateOverrideReq(BaseModel):
    dates: List[str]
    quota: Optional[int] = None

