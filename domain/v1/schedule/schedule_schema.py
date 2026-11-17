"""
[일정 관리 Pydantic V2 스키마 (domain/v1/schedule/schedule_schema.py)]
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


VALID_CATEGORIES = {"PERSONAL", "ATTENDANCE", "OFFICE", "GLOBAL", "HOLIDAY"}
VALID_DISPLAY_MODES = {"bar", "background"}
VALID_FREQS = {"NONE", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


def _parse_dt(val: object) -> Optional[datetime]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if len(s) == 10:
            return datetime.fromisoformat(f"{s}T00:00:00")
        return datetime.fromisoformat(s)
    raise ValueError(f"유효하지 않은 날짜/시간 형식입니다: {val}")


class RecurrenceRule(BaseModel):
    freq: str = "NONE"  # NONE | DAILY | WEEKLY | MONTHLY | YEARLY
    interval: int = Field(default=1, ge=1, le=99)
    byDay: List[str] = Field(default_factory=list)
    byMonthDay: Optional[int] = Field(default=None, ge=1, le=31)
    until: Optional[str] = None
    count: Optional[int] = Field(default=None, ge=1, le=365)

    @field_validator("freq")
    @classmethod
    def check_freq(cls, v: str) -> str:
        norm = (v or "NONE").strip().upper()
        if norm not in VALID_FREQS:
            raise ValueError(f"지원되지 않는 반복 주기입니다: {v}")
        return norm


class ScheduleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    category: str = "PERSONAL"
    color: str = "#3b82f6"
    start_at: datetime
    end_at: Optional[datetime] = None
    is_all_day: bool = False
    display_mode: str = "bar"
    importance: int = Field(default=1, ge=1, le=5)
    is_dday: bool = False
    recurrence: Optional[RecurrenceRule] = None

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def parse_dates(cls, v):
        return _parse_dt(v)

    @field_validator("category")
    @classmethod
    def check_category(cls, v: str) -> str:
        norm = (v or "PERSONAL").strip().upper()
        if norm not in VALID_CATEGORIES:
            raise ValueError(f"유효하지 않은 카테고리입니다: {v}")
        return norm

    @field_validator("display_mode")
    @classmethod
    def check_display_mode(cls, v: str) -> str:
        norm = (v or "bar").strip().lower()
        if norm not in VALID_DISPLAY_MODES:
            return "bar"
        return norm


class ScheduleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    is_all_day: Optional[bool] = None
    display_mode: Optional[str] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    is_dday: Optional[bool] = None
    recurrence: Optional[RecurrenceRule] = None

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def parse_dates(cls, v):
        return _parse_dt(v)

    @field_validator("category")
    @classmethod
    def check_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        norm = v.strip().upper()
        if norm not in VALID_CATEGORIES:
            raise ValueError(f"유효하지 않은 카테고리입니다: {v}")
        return norm
