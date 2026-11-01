"""
============================================================================
[미니앱 통합 액션 아이템 Pydantic 스키마 (miniapp_schema.py)]
============================================================================
"""

from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, ConfigDict


class MiniappItemBase(BaseModel):
    category: str = "MEMO"  # MEMO, ALARM, INSTRUCTION, MESSAGE, NOTIFICATION
    title: Optional[str] = None
    content: str
    target_time: Optional[datetime] = None
    link: Optional[str] = None
    extra_payload: Optional[Dict[str, Any]] = None


class MiniappItemCreate(MiniappItemBase):
    """신규 미니앱 아이템 생성 요청"""
    receiver_id: Optional[int] = None  # None이면 본인(MEMO) 또는 전사공지(NOTIFICATION)


class MiniappItemUpdate(BaseModel):
    """미니앱 아이템 상태/내용 변경 요청"""
    status: Optional[str] = None  # PENDING, ONGOING, COMPLETED, READ
    title: Optional[str] = None
    content: Optional[str] = None
    target_time: Optional[datetime] = None
    extra_payload: Optional[Dict[str, Any]] = None


class MiniappItemResponse(BaseModel):
    """미니앱 단일 아이템 응답"""
    id: int
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    receiver_id: Optional[int] = None
    category: str
    title: Optional[str] = None
    content: str
    status: str
    target_time: Optional[datetime] = None
    link: Optional[str] = None
    extra_payload: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MiniappCountsResponse(BaseModel):
    """
    상단 헤더 뱃지 및 슬라이더 뱃지용 실시간 미결 카운트
    """
    NOTIFICATION: int = 0
    INSTRUCTION: int = 0
    MESSAGE: int = 0
    MEMO: int = 0
    ALARM: int = 0
    TOTAL: int = 0
