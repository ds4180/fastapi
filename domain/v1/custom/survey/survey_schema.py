"""
============================================================================
[현장 조사·설문 Pydantic 스키마 (domain/v1/custom/survey/survey_schema.py)]
============================================================================
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SurveyCampaignCreate(BaseModel):
    code: Optional[str] = Field(None, max_length=64, description="식별 코드 (미입력 시 자동 생성)")
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field("GENERAL", max_length=50)
    description: Optional[str] = None
    submit_scope: Literal["USER", "VEHICLE"] = "USER"
    target_type: Literal["ALL", "GROUP", "USER"] = "ALL"
    target_groups: List[str] = Field(default_factory=list)
    target_user_ids: List[int] = Field(default_factory=list)
    form_schema: List[Dict[str, Any]] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["DRAFT", "OPEN", "CLOSED", "ARCHIVED"] = "DRAFT"
    start_at: Optional[datetime] = None
    due_at: Optional[datetime] = None


class SurveyCampaignUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=64)
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    submit_scope: Optional[Literal["USER", "VEHICLE"]] = None
    target_type: Optional[Literal["ALL", "GROUP", "USER"]] = None
    target_groups: Optional[List[str]] = None
    target_user_ids: Optional[List[int]] = None
    form_schema: Optional[List[Dict[str, Any]]] = None
    options: Optional[Dict[str, Any]] = None
    status: Optional[Literal["DRAFT", "OPEN", "CLOSED", "ARCHIVED"]] = None
    start_at: Optional[datetime] = None
    due_at: Optional[datetime] = None


class SurveySubmitPayload(BaseModel):
    vehicle_no: Optional[str] = Field(None, max_length=30)
    answers: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["DRAFT", "SUBMITTED"] = "SUBMITTED"
    source_app_id: str = Field("survey", max_length=50)
    source_ref_id: Optional[str] = Field(None, max_length=100)


class SurveyTemplateSave(BaseModel):
    id: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field("GENERAL", max_length=50)
    description: Optional[str] = None
    submit_scope: Literal["USER", "VEHICLE"] = "USER"
    form_schema: List[Dict[str, Any]] = Field(default_factory=list)
