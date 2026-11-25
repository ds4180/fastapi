"""
[블랙박스 비디오 관리 Pydantic V2 스키마 (blackbox_schema.py)]
"""

from datetime import date, datetime
import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


def _normalize_display_num(v: str) -> str:
    s = (v or "").strip()
    if not re.fullmatch(r"\d{1,3}", s):
        raise ValueError("육안 식별 번호(display_num)는 0부터 999 사이의 숫자(최대 3자리)여야 합니다.")
    num = int(s)
    if num < 0 or num > 999:
        raise ValueError("육안 식별 번호(display_num)는 0부터 999 사이여야 합니다.")
    return str(num)


# ============================================================================
# 1. 차량 블랙박스 본체 (Device)
# ============================================================================
class DeviceCreate(BaseModel):
    vehicle_no: str = Field(..., min_length=1, max_length=50)
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    channels: Optional[str] = None
    led_count: int = Field(default=0, ge=0, le=99)
    serial_no: Optional[str] = None
    installed_date: Optional[date] = None
    status: str = "NORMAL"
    notes: Optional[str] = None


class DeviceUpdate(BaseModel):
    vehicle_no: Optional[str] = Field(default=None, min_length=1, max_length=50)
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    channels: Optional[str] = None
    led_count: Optional[int] = Field(default=None, ge=0, le=99)
    serial_no: Optional[str] = None
    installed_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# 2. 비디오 장부 (Video)
# ============================================================================
class VideoCreate(BaseModel):
    video_no: Optional[str] = Field(default=None, max_length=50)
    display_num: str = Field(..., min_length=1, max_length=3)
    manufacturer: Optional[str] = None
    spec: Optional[str] = None
    serial_no: Optional[str] = None
    purchase_date: Optional[date] = None
    disposal_date: Optional[date] = None
    location_type: str = "OFFICE"  # OFFICE | VEHICLE
    current_vehicle_no: Optional[str] = None
    mounted_at: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("display_num")
    @classmethod
    def check_display_num(cls, v: str) -> str:
        return _normalize_display_num(v)

    @field_validator("location_type")
    @classmethod
    def check_location_type(cls, v: str) -> str:
        norm = (v or "OFFICE").strip().upper()
        if norm not in {"OFFICE", "VEHICLE"}:
            raise ValueError("위치 구분(location_type)은 반드시 OFFICE 또는 VEHICLE 이어야 합니다.")
        return norm


class VideoUpdate(BaseModel):
    video_no: Optional[str] = Field(default=None, min_length=1, max_length=50)
    display_num: Optional[str] = None
    manufacturer: Optional[str] = None
    spec: Optional[str] = None
    serial_no: Optional[str] = None
    purchase_date: Optional[date] = None
    disposal_date: Optional[date] = None
    notes: Optional[str] = None

    @field_validator("display_num")
    @classmethod
    def check_display_num(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _normalize_display_num(v)


class VideoMountReq(BaseModel):
    vehicle_no: str = Field(..., min_length=1, max_length=50)
    mounted_at: Optional[datetime] = None
    notes: Optional[str] = None
    auto_swap: bool = True


class VideoUnmountReq(BaseModel):
    removed_at: Optional[datetime] = None
    notes: Optional[str] = None


# ============================================================================
# 3. 운전기사 교체 요청 (Request)
# ============================================================================
class DriverRequestCreate(BaseModel):
    vehicle_no: str = Field(..., min_length=1, max_length=50)
    reason_type: str = "CHECK"
    reason_detail: Optional[str] = None
    incident_date: Optional[datetime] = None

    @field_validator("incident_date", mode="before")
    @classmethod
    def parse_incident_date(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str) and len(v.strip()) == 10:
            return datetime.fromisoformat(f"{v.strip()}T00:00:00")
        return v


class AdminRequestProcess(BaseModel):
    status: str  # PREPARING | COMPLETED | REJECTED
    replacement_video_id: Optional[int] = None
    admin_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        norm = (v or "").strip().upper()
        if norm not in {"PREPARING", "COMPLETED", "REJECTED"}:
            raise ValueError("처리 상태(status)는 PREPARING, COMPLETED 또는 REJECTED 이어야 합니다.")
        return norm
