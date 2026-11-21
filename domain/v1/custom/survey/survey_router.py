"""
============================================================================
[현장 조사·설문 라우터 (domain/v1/custom/survey/survey_router.py)]
============================================================================
- 사용자/서비스앱 라우터: /v1/survey
- 관리자 관제 라우터: /v1/admin/survey
"""

from datetime import datetime
import re
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_db
from core.deps import get_current_user, require_app_permission
from core.audit import safe_log_audit
from models import SurveyCampaign, SurveyResponse, User

from . import survey_schema as schema
from . import survey_service as service

router = APIRouter(prefix="/v1/survey", tags=["Custom Survey"])
admin_router = APIRouter(prefix="/v1/admin/survey", tags=["Admin Survey"])

check_survey_read = require_app_permission("survey", action="read")
check_survey_write = require_app_permission("survey", action="write")


def _notify_survey_targets(
    db: Session,
    *,
    campaign: SurveyCampaign,
    sender: User,
    target_user_ids: List[int],
    title: str,
    message: str,
    background_tasks: BackgroundTasks,
):
    if not target_user_ids:
        return
    from core.notify import safe_notify
    from domain.push.push_service import (
        is_push_domain_enabled,
        dispatch_push_async,
        send_push_to_users,
    )

    push_enabled = is_push_domain_enabled(db, "survey_request")
    target_url = f"/v1/custom/survey/{campaign.id}"
    plain_message = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", message or "")).strip() or "새로운 조사 양식이 배포되었습니다. 확인 후 작성해 주세요."
    if len(plain_message) > 140:
        plain_message = plain_message[:137] + "..."

    safe_notify(
        db=db,
        category="NOTIFICATION",
        title=title,
        message=plain_message,
        sender=sender,
        target_user_ids=target_user_ids,
        level=2,
        link=target_url,
        background_tasks=background_tasks,
        extra_payload={"campaign_id": campaign.id, "send_web_push": False},
    )

    if push_enabled and campaign.options.get("push_on_open", True):
        dispatch_push_async(
            send_push_to_users,
            user_ids=target_user_ids,
            title=title,
            body=plain_message,
            url=target_url,
        )


# ============================================================================
# 1. 사용자 참여 & 서비스앱(SERVICE) 엔드포인트 (/v1/survey)
# ============================================================================
@router.get("/vehicles")
def get_survey_vehicle_context(current_user: User = Depends(get_current_user)):
    """차량별 조사에 활용할 차량 풀과 사원의 기본 배정 차량을 반환합니다."""
    return service.get_vehicle_context(current_user)


@router.get("/my-list")
def list_my_surveys(
    include_closed: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """로그인 사원에게 열려있는 조사 및 과거 참여 조사 목록을 조회합니다."""
    allowed_statuses = ["OPEN", "CLOSED"] if include_closed else ["OPEN"]
    campaigns = (
        db.query(SurveyCampaign)
        .filter(
            SurveyCampaign.is_deleted == False,
            SurveyCampaign.status.in_(allowed_statuses),
        )
        .order_by(SurveyCampaign.status.desc(), SurveyCampaign.created_at.desc())
        .all()
    )

    my_rows = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.user_id == current_user.id,
            SurveyResponse.is_deleted == False,
        )
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )
    my_by_campaign = {}
    for r in my_rows:
        my_by_campaign.setdefault(r.campaign_id, []).append(service.serialize_response(r))

    result = []
    is_admin = current_user.rank() >= 4
    for c in campaigns:
        my_list = my_by_campaign.get(c.id, [])
        if not service.is_user_targeted(c, current_user) and not my_list and not is_admin:
            continue
        result.append(
            service.serialize_campaign(
                c,
                my_response=my_list[0] if my_list else None,
                my_responses=my_list,
            )
        )

    return {
        "campaigns": result,
        "vehicle_context": service.get_vehicle_context(current_user),
    }


@router.get("/by-code/{code}")
def get_survey_by_code(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """서비스앱(SERVICE) 임베드 및 코드 기반 단축 조회 엔드포인트입니다."""
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.code == code, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="해당 코드의 조사 양식을 찾을 수 없습니다.")

    my_rows = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.campaign_id == c.id,
            SurveyResponse.user_id == current_user.id,
            SurveyResponse.is_deleted == False,
        )
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )
    serialized = [service.serialize_response(r) for r in my_rows]
    return {
        "campaign": service.serialize_campaign(
            c,
            my_response=serialized[0] if serialized else None,
            my_responses=serialized,
        ),
        "vehicle_context": service.get_vehicle_context(current_user),
    }


@router.get("/{campaign_id}")
def get_survey_detail(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """특정 조사 양식 및 본인의 기존 응답 목록을 조회합니다."""
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="조사 양식을 찾을 수 없습니다.")

    my_rows = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.campaign_id == c.id,
            SurveyResponse.user_id == current_user.id,
            SurveyResponse.is_deleted == False,
        )
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )
    if c.status == "DRAFT" and current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="아직 배포되지 않은 조사입니다.")

    serialized = [service.serialize_response(r) for r in my_rows]
    return {
        "campaign": service.serialize_campaign(
            c,
            my_response=serialized[0] if serialized else None,
            my_responses=serialized,
        ),
        "vehicle_context": service.get_vehicle_context(current_user),
    }


@router.post("/{campaign_id}/submit")
def submit_survey_response(
    campaign_id: int,
    payload: schema.SurveySubmitPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """조사 양식 응답을 제출하거나 수정 저장합니다."""
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="조사 양식을 찾을 수 없습니다.")

    if not service.is_user_targeted(c, current_user) and current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="이 조사의 참여 대상이 아닙니다.")

    row = service.upsert_response(
        db,
        c,
        current_user,
        vehicle_no=payload.vehicle_no,
        answers=payload.answers,
        status_val=payload.status,
        source_app_id=payload.source_app_id,
        source_ref_id=payload.source_ref_id,
    )
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_SUBMIT",
        title=f"[조사제출] {c.title}",
        user=current_user,
        resource_type="survey_response",
        resource_id=str(row.id),
        message=f"'{current_user.real_name or current_user.username}'이(가) 조사 '{c.title}' 응답을 저장했습니다."
        + (f" (차량 {row.vehicle_no})" if row.vehicle_no else ""),
    )
    return {
        "message": "응답이 저장되었습니다.",
        "response": service.serialize_response(row),
    }


# ============================================================================
# 2. 관리자 관제·빌더·통계·과거이력 엔드포인트 (/v1/admin/survey)
# ============================================================================
@admin_router.get("/campaigns")
def admin_list_campaigns(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_read),
):
    """전체 조사 캠페인(진행 중 + 과거 이력)과 응답/이상 건수를 조회합니다."""
    q = db.query(SurveyCampaign).filter(SurveyCampaign.is_deleted == False)
    if status:
        q = q.filter(SurveyCampaign.status == status)
    if category:
        q = q.filter(SurveyCampaign.category == category)
    if year:
        q = q.filter(func.extract("year", SurveyCampaign.created_at) == year)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.filter((SurveyCampaign.title.ilike(kw)) | (SurveyCampaign.code.ilike(kw)))

    campaigns = q.order_by(SurveyCampaign.created_at.desc(), SurveyCampaign.id.desc()).all()

    counts_rows = (
        db.query(
            SurveyResponse.campaign_id,
            func.count(SurveyResponse.id),
        )
        .filter(SurveyResponse.is_deleted == False, SurveyResponse.status == "SUBMITTED")
        .group_by(SurveyResponse.campaign_id)
        .all()
    )
    issue_rows = (
        db.query(
            SurveyResponse.campaign_id,
            func.count(SurveyResponse.id),
        )
        .filter(
            SurveyResponse.is_deleted == False,
            SurveyResponse.status == "SUBMITTED",
            SurveyResponse.has_issue == True,
        )
        .group_by(SurveyResponse.campaign_id)
        .all()
    )
    count_map = {cid: cnt for cid, cnt in counts_rows}
    issue_map = {cid: cnt for cid, cnt in issue_rows}

    result = []
    for c in campaigns:
        target_users = service.resolve_campaign_target_users(db, c)
        result.append(
            service.serialize_campaign(
                c,
                response_count=count_map.get(c.id, 0),
                target_count=len(target_users),
                issue_count=issue_map.get(c.id, 0),
            )
        )
    return {"campaigns": result}


@admin_router.post("/campaigns")
def admin_create_campaign(
    payload: schema.SurveyCampaignCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    code = (payload.code or "").strip() or service.generate_campaign_code(payload.title)
    if db.query(SurveyCampaign).filter(SurveyCampaign.code == code).first():
        raise HTTPException(status_code=400, detail=f"이미 사용 중인 캠페인 코드입니다: {code}")

    c = SurveyCampaign(
        code=code,
        title=payload.title.strip(),
        category=payload.category,
        description=payload.description,
        submit_scope=payload.submit_scope,
        target_type=payload.target_type,
        target_groups=payload.target_groups,
        target_user_ids=payload.target_user_ids,
        form_schema=payload.form_schema,
        schema_version=1,
        options=payload.options or {"allow_edit": True, "push_on_open": True},
        status=payload.status,
        start_at=payload.start_at,
        due_at=payload.due_at,
        created_by=admin.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_CREATE",
        title=f"조사 양식 생성: {c.title}",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
        message=f"관리자 '{admin.username}'이(가) 조사 캠페인 '{c.title}'({c.code})를 생성했습니다.",
    )

    if c.status == "OPEN":
        target_ids = [u.id for u in service.resolve_campaign_target_users(db, c)]
        _notify_survey_targets(
            db,
            campaign=c,
            sender=admin,
            target_user_ids=target_ids,
            title=f"[현장 조사 요청] {c.title}",
            message=c.description or "새로운 조사 양식이 배포되었습니다. 확인 후 작성해 주세요.",
            background_tasks=background_tasks,
        )

    return {"message": "생성되었습니다.", "campaign": service.serialize_campaign(c)}


@admin_router.put("/campaigns/{campaign_id}")
def admin_update_campaign(
    campaign_id: int,
    payload: schema.SurveyCampaignUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    if payload.code and payload.code.strip() != c.code:
        dup = db.query(SurveyCampaign).filter(SurveyCampaign.code == payload.code.strip()).first()
        if dup:
            raise HTTPException(status_code=400, detail="이미 사용 중인 캠페인 코드입니다.")
        c.code = payload.code.strip()

    schema_changed = payload.form_schema is not None and payload.form_schema != c.form_schema
    for attr in (
        "title",
        "category",
        "description",
        "submit_scope",
        "target_type",
        "target_groups",
        "target_user_ids",
        "form_schema",
        "options",
        "status",
        "start_at",
        "due_at",
    ):
        val = getattr(payload, attr)
        if val is not None:
            setattr(c, attr, val)

    if schema_changed:
        c.schema_version = (c.schema_version or 1) + 1
    c.updated_at = datetime.now()
    db.commit()
    db.refresh(c)

    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_UPDATE",
        title=f"조사 양식 수정: {c.title}",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
    )
    return {"message": "수정되었습니다.", "campaign": service.serialize_campaign(c)}


@admin_router.delete("/campaigns/{campaign_id}")
def admin_delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")
    c.is_deleted = True
    c.updated_at = datetime.now()
    db.commit()
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_DELETE",
        title=f"조사 삭제(소프트): {c.title}",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
    )
    return {"message": "삭제되었습니다."}


@admin_router.post("/campaigns/{campaign_id}/publish")
def admin_publish_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")
    c.status = "OPEN"
    if not c.start_at:
        c.start_at = datetime.now()
    c.updated_at = datetime.now()
    db.commit()

    target_ids = [u.id for u in service.resolve_campaign_target_users(db, c)]
    _notify_survey_targets(
        db,
        campaign=c,
        sender=admin,
        target_user_ids=target_ids,
        title=f"[현장 조사 요청] {c.title}",
        message=c.description or "새로운 조사 양식이 배포되었습니다. 확인 후 작성해 주세요.",
        background_tasks=background_tasks,
    )
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_PUBLISH",
        title=f"조사 배포: {c.title} ({len(target_ids)}명)",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
    )
    return {"message": f"조사가 배포되었습니다. (대상 {len(target_ids)}명)", "target_count": len(target_ids)}


@admin_router.post("/campaigns/{campaign_id}/close")
def admin_close_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")
    c.status = "CLOSED"
    c.updated_at = datetime.now()
    db.commit()
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_CLOSE",
        title=f"조사 마감: {c.title}",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
    )
    return {"message": "조사가 마감되었습니다."}


@admin_router.post("/campaigns/{campaign_id}/remind")
def admin_remind_missing_users(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    stats = service.build_campaign_stats(db, c)
    missing_ids = [u["id"] for u in stats["summary"]["missing_users"]]
    if not missing_ids:
        return {"message": "미제출자가 없습니다.", "sent_count": 0}

    _notify_survey_targets(
        db,
        campaign=c,
        sender=admin,
        target_user_ids=missing_ids,
        title=f"[미제출 독촉] {c.title}",
        message="아직 제출하지 않은 조사 양식이 있습니다. 확인 후 작성을 완료해 주세요.",
        background_tasks=background_tasks,
    )
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_REMIND",
        title=f"미제출 독촉 발송: {c.title} ({len(missing_ids)}명)",
        user=admin,
        resource_type="survey_campaign",
        resource_id=str(c.id),
    )
    return {"message": f"미제출자 {len(missing_ids)}명에게 독촉 알림을 발송했습니다.", "sent_count": len(missing_ids)}


@admin_router.get("/campaigns/{campaign_id}/responses")
def admin_list_responses(
    campaign_id: int,
    only_issue: bool = Query(False),
    vehicle_no: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_read),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    q = (
        db.query(SurveyResponse)
        .options(joinedload(SurveyResponse.user))
        .filter(SurveyResponse.campaign_id == c.id, SurveyResponse.is_deleted == False)
    )
    if only_issue:
        q = q.filter(SurveyResponse.has_issue == True)
    if vehicle_no and vehicle_no.strip():
        q = q.filter(SurveyResponse.vehicle_no.ilike(f"%{vehicle_no.strip()}%"))

    rows = q.order_by(SurveyResponse.submitted_at.desc(), SurveyResponse.id.desc()).all()
    serialized = [service.serialize_response(r) for r in rows]

    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        serialized = [
            item for item in serialized
            if kw in (item["submitter_name"] or "").lower()
            or kw in (item["vehicle_no"] or "").lower()
            or kw in str(item["answers"]).lower()
        ]

    return {
        "campaign": service.serialize_campaign(c),
        "responses": serialized,
    }


@admin_router.get("/campaigns/{campaign_id}/stats")
def admin_get_campaign_stats(
    campaign_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_read),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")
    return {
        "campaign": service.serialize_campaign(c),
        "stats": service.build_campaign_stats(db, c),
    }


@admin_router.get("/campaigns/{campaign_id}/export")
def admin_export_campaign_csv(
    campaign_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_read),
):
    c = (
        db.query(SurveyCampaign)
        .filter(SurveyCampaign.id == campaign_id, SurveyCampaign.is_deleted == False)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    csv_text = service.build_campaign_csv(db, c)
    filename = quote(f"survey_{c.code}.csv")
    return StreamingResponse(
        iter([csv_text.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@admin_router.get("/templates")
def admin_list_templates(
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_read),
):
    """저장된 사용자 정의 템플릿과 기본 내장 템플릿 목록을 조회합니다."""
    return {"templates": service.list_survey_templates(db)}


@admin_router.post("/templates")
def admin_save_template(
    payload: schema.SurveyTemplateSave,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    """현재 조사 양식을 재사용 가능한 템플릿으로 저장합니다."""
    tpl = service.save_survey_template(db, payload.model_dump(), user=admin)
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_TEMPLATE_SAVE",
        title=f"조사 템플릿 저장: {tpl['name']}",
        user=admin,
        resource_type="system_config",
        resource_id=service.SURVEY_TEMPLATES_KEY,
    )
    return {"message": f"템플릿 '{tpl['name']}'이(가) 저장되었습니다.", "template": tpl}


@admin_router.delete("/templates/{template_id}")
def admin_delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(check_survey_write),
):
    """저장된 사용자 정의 조사 템플릿을 삭제합니다."""
    service.delete_survey_template(db, template_id)
    safe_log_audit(
        db=db,
        app_id="survey",
        log_type="CHANGE",
        action="SURVEY_TEMPLATE_DELETE",
        title=f"조사 템플릿 삭제: {template_id}",
        user=admin,
        resource_type="system_config",
        resource_id=service.SURVEY_TEMPLATES_KEY,
    )
    return {"message": "템플릿이 삭제되었습니다."}
