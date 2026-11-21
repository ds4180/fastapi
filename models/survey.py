"""
============================================================================
[현장 조사·설문 모델 (models/survey.py)]
============================================================================

💡 이 파일의 역할:
- SurveyCampaign : 사무실(관리자)이 JSONB 동적 양식(form_schema)으로 생성·배포하는 조사/설문 요청서
- SurveyResponse : 사원/운전원이 제출하는 JSONB 응답 원장 (과거 이력 스냅샷, 이상 항목 플래그, 서비스앱 유입 메타 포함)
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    and_,
)
from sqlalchemy.orm import relationship
from models.base import Base, JSONType


class SurveyCampaign(Base):
    """조사·설문 캠페인 마스터 모델"""

    __tablename__ = "survey_campaigns"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, default="GENERAL", index=True)
    description = Column(Text, nullable=True)

    # 제출 단위: USER(1인 1건) | VEHICLE(차량별 1건)
    submit_scope = Column(String(20), nullable=False, default="USER")

    # 대상 지정: ALL | GROUP | USER
    target_type = Column(String(20), nullable=False, default="ALL")
    target_groups = Column(JSONType, nullable=False, default=list)
    target_user_ids = Column(JSONType, nullable=False, default=list)

    # 동적 양식 정의 (JSONB 배열) 및 버전
    form_schema = Column(JSONType, nullable=False, default=list)
    schema_version = Column(Integer, nullable=False, default=1)

    # 부가 옵션 (allow_edit, anonymous, push_on_open, require_vehicle 등)
    options = Column(JSONType, nullable=False, default=dict)

    # 상태: DRAFT | OPEN | CLOSED | ARCHIVED
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    start_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    is_deleted = Column(Boolean, nullable=False, default=False)

    creator = relationship("User", foreign_keys=[created_by])
    responses = relationship(
        "SurveyResponse",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SurveyResponse.submitted_at.desc()",
    )


class SurveyResponse(Base):
    """조사·설문 응답 원장 및 과거 이력 모델"""

    __tablename__ = "survey_responses"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(
        Integer,
        ForeignKey("survey_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 제출 시점 사원 정보 스냅샷 (퇴사/부서이동 후에도 과거 이력 보존)
    submitter_snapshot = Column(JSONType, nullable=False, default=dict)

    # 차량별 조사(submit_scope='VEHICLE') 시 차량번호
    vehicle_no = Column(String(30), nullable=True, index=True)

    # 실제 답변 JSONB (GIN 인덱스 대상)
    answers = Column(JSONType, nullable=False, default=dict)
    schema_version = Column(Integer, nullable=False, default=1)
    form_snapshot = Column(JSONType, nullable=True)

    # 이상/교체/불량 항목 포함 여부 (통계 필터 고속화용 자동 판정)
    has_issue = Column(Boolean, nullable=False, default=False, index=True)

    # 단독(survey) 및 서비스앱(board/page) 유입 경로 추적
    source_app_id = Column(String(50), nullable=False, default="survey")
    source_ref_id = Column(String(100), nullable=True)

    # 상태: DRAFT | SUBMITTED
    status = Column(String(20), nullable=False, default="SUBMITTED")
    submitted_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    is_deleted = Column(Boolean, nullable=False, default=False)

    campaign = relationship("SurveyCampaign", back_populates="responses")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        # USER 단위: 동일 캠페인 + 동일 사원(차량번호 없음) 중복 방지
        Index(
            "ix_survey_responses_campaign_user_active",
            "campaign_id",
            "user_id",
            unique=True,
            postgresql_where=and_(is_deleted == False, vehicle_no.is_(None)),
        ),
        # VEHICLE 단위: 동일 캠페인 + 동일 차량 중복 방지
        Index(
            "ix_survey_responses_campaign_vehicle_active",
            "campaign_id",
            "vehicle_no",
            unique=True,
            postgresql_where=and_(is_deleted == False, vehicle_no.isnot(None)),
        ),
        # 이상 항목 고속 필터링용 복합 인덱스
        Index(
            "ix_survey_responses_campaign_issue_active",
            "campaign_id",
            "has_issue",
            postgresql_where=(is_deleted == False),
        ),
        # PostgreSQL JSONB GIN 인덱스 (답변 내용 고속 검색/통계)
        Index(
            "ix_survey_responses_answers_gin",
            "answers",
            postgresql_using="gin",
            postgresql_ops={"answers": "jsonb_path_ops"},
        ),
    )
