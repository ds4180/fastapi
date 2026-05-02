from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

class Alert(BaseModel):
    """
    업무 지시 및 알림 응답 스키마
    """
    id: int
    message: str
    level: int
    style: str
    position: str
    route: Optional[str] = None
    redirect_url: Optional[str] = None
    is_active: bool
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    target_users: Optional[str] = None
    confirm_text: str
    reset_sec: int
    create_date: datetime

    model_config = ConfigDict(from_attributes=True)

class AlertCreate(BaseModel):
    """
    업무 지시 및 알림 생성 스키마
    """
    message: str
    level: int = 1
    style: str = "info"
    position: str = "top"
    route: Optional[str] = None
    redirect_url: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    target_users: Optional[str] = None
    confirm_text: str = "확인하였습니다"
    reset_sec: int = 0

class AlertUpdate(BaseModel):
    """
    업무 지시 및 알림 수정 스키마
    """
    message: Optional[str] = None
    level: Optional[int] = None
    style: Optional[str] = None
    position: Optional[str] = None
    route: Optional[str] = None
    redirect_url: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    target_users: Optional[str] = None
    confirm_text: Optional[str] = None
    reset_sec: Optional[int] = None
    is_active: Optional[bool] = None

class AlertList(BaseModel):
    """
    알림 목록 응답 스키마
    """
    alerts: list[Alert]
