"""
============================================================================
[현장 조사·설문 비즈니스 로직 & 통계 엔진 (domain/v1/custom/survey/survey_service.py)]
============================================================================
"""

from __future__ import annotations
import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from models import SurveyCampaign, SurveyResponse, SystemConfig, User
from core.permission import get_user_groups


def generate_campaign_code(title: str) -> str:
    prefix = datetime.now().strftime("%Y%m%d")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    if not slug:
        slug = "survey"
    suffix = datetime.now().strftime("%H%M%S")
    return f"{prefix}-{slug[:32]}-{suffix}"


def get_vehicle_context(user: Optional[User] = None) -> Dict[str, Any]:
    """등록된 차량 풀과 로그인 사원의 기본 배정 차량을 반환합니다."""
    vehicles: List[Dict[str, str]] = []
    default_vehicle: Optional[str] = None
    try:
        from domain.v1.custom.blackbox.blackbox_crud import get_vehicle_pool
        vehicles = get_vehicle_pool()
    except Exception:
        vehicles = []

    if user is not None:
        try:
            from domain.v1.dispatch.dispatch_builder import load_drivers_metadata
            _, vehicle_map, _ = load_drivers_metadata()
            for candidate in (getattr(user, "real_name", None), getattr(user, "username", None)):
                if candidate and candidate.strip() in vehicle_map:
                    default_vehicle = vehicle_map[candidate.strip()]
                    break
        except Exception:
            default_vehicle = None

    routes = sorted({v["route"] for v in vehicles if v.get("route")})
    return {
        "vehicles": vehicles,
        "routes": routes,
        "my_default_vehicle": default_vehicle,
    }


def serialize_campaign(
    c: SurveyCampaign,
    *,
    response_count: Optional[int] = None,
    target_count: Optional[int] = None,
    issue_count: Optional[int] = None,
    my_response: Optional[Dict[str, Any]] = None,
    my_responses: Optional[List[Dict[str, Any]]] = None,
    target_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": c.id,
        "code": c.code,
        "title": c.title,
        "category": c.category,
        "description": c.description,
        "submit_scope": c.submit_scope,
        "target_type": c.target_type,
        "target_groups": c.target_groups or [],
        "target_user_ids": c.target_user_ids or [],
        "form_schema": c.form_schema or [],
        "schema_version": c.schema_version,
        "options": c.options or {},
        "status": c.status,
        "start_at": c.start_at.isoformat() if c.start_at else None,
        "due_at": c.due_at.isoformat() if c.due_at else None,
        "created_by": c.created_by,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else None,
        "updated_at": c.updated_at.strftime("%Y-%m-%d %H:%M") if c.updated_at else None,
    }
    if response_count is not None:
        data["response_count"] = response_count
    if target_count is not None:
        data["target_count"] = target_count
    if issue_count is not None:
        data["issue_count"] = issue_count
    if my_response is not None:
        data["my_response"] = my_response
    if my_responses is not None:
        data["my_responses"] = my_responses
    if target_status is not None:
        data["target_status"] = target_status
    return data


def serialize_response(r: SurveyResponse) -> Dict[str, Any]:
    snap = r.submitter_snapshot or {}
    return {
        "id": r.id,
        "campaign_id": r.campaign_id,
        "user_id": r.user_id,
        "submitter_snapshot": snap,
        "submitter_name": snap.get("real_name") or snap.get("username") or (r.user.real_name if r.user else "-"),
        "submitter_group": snap.get("primary_group") or "",
        "vehicle_no": r.vehicle_no,
        "answers": r.answers or {},
        "schema_version": r.schema_version,
        "form_snapshot": r.form_snapshot,
        "has_issue": bool(r.has_issue),
        "source_app_id": r.source_app_id,
        "source_ref_id": r.source_ref_id,
        "status": r.status,
        "submitted_at": r.submitted_at.strftime("%Y-%m-%d %H:%M") if r.submitted_at else None,
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else None,
    }


def resolve_campaign_target_users(db: Session, campaign: SurveyCampaign) -> List[User]:
    """캠페인 대상 조건에 해당하는 활성 사원 목록을 반환합니다."""
    users = db.query(User).options(joinedload(User.profile)).all()
    active_users = [
        u for u in users
        if u.profile is None or u.profile.is_active is not False
    ]

    if campaign.target_type == "ALL":
        return active_users

    if campaign.target_type == "USER":
        id_set = {int(uid) for uid in (campaign.target_user_ids or []) if str(uid).isdigit()}
        return [u for u in active_users if u.id in id_set]

    if campaign.target_type == "GROUP":
        grp_set = {str(g) for g in (campaign.target_groups or []) if g}
        if not grp_set:
            return []
        return [u for u in active_users if bool(get_user_groups(u) & grp_set)]

    return []


def is_user_targeted(campaign: SurveyCampaign, user: User) -> bool:
    if campaign.target_type == "ALL":
        return True
    if campaign.target_type == "USER":
        id_set = {int(uid) for uid in (campaign.target_user_ids or []) if str(uid).isdigit()}
        return user.id in id_set
    if campaign.target_type == "GROUP":
        grp_set = {str(g) for g in (campaign.target_groups or []) if g}
        return bool(get_user_groups(user) & grp_set)
    return False


def _extract_vehicle_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def resolve_campaign_target_vehicles(campaign: SurveyCampaign) -> List[Dict[str, str]]:
    """차량별 조사 캠페인의 대상 차량 목록({vehicle_no, route})을 반환합니다."""
    vehicles = get_vehicle_context(None).get("vehicles") or []
    opts = campaign.options if isinstance(campaign.options, dict) else {}
    vt = opts.get("vehicle_target") if isinstance(opts.get("vehicle_target"), dict) else {}
    mode = str(vt.get("mode") or "ALL").upper()

    if mode == "ALL":
        return vehicles

    if mode == "ROUTE":
        route_set = {str(r).strip() for r in (vt.get("routes") or []) if str(r).strip()}
        if not route_set:
            return []
        return [v for v in vehicles if v.get("route") in route_set]

    if mode == "VEHICLE":
        vno_set = {str(x).strip() for x in (vt.get("vehicle_nos") or []) if str(x).strip()}
        if not vno_set:
            return []
        return [v for v in vehicles if v.get("vehicle_no") in vno_set]

    if mode == "RANGE":
        raw_start = str(vt.get("range_start") or "").strip()
        raw_end = str(vt.get("range_end") or "").strip()
        if not raw_start and not raw_end:
            return vehicles
        s_num = _extract_vehicle_int(raw_start)
        e_num = _extract_vehicle_int(raw_end)
        matched: List[Dict[str, str]] = []
        for v in vehicles:
            vno = str(v.get("vehicle_no") or "").strip()
            v_num = _extract_vehicle_int(vno)
            if v_num is not None and (s_num is not None or e_num is not None):
                if s_num is not None and v_num < s_num:
                    continue
                if e_num is not None and v_num > e_num:
                    continue
                matched.append(v)
            else:
                if raw_start and vno < raw_start:
                    continue
                if raw_end and vno > raw_end:
                    continue
                matched.append(v)
        return matched

    return vehicles


def build_campaign_target_status(
    db: Session,
    campaign: SurveyCampaign,
    responses: Optional[List[SurveyResponse]] = None,
) -> Dict[str, Any]:
    """캠페인의 전체 대상 목록과 각 대상별 작성 여부 및 작성자 정보를 반환합니다."""
    if responses is None:
        responses = (
            db.query(SurveyResponse)
            .options(joinedload(SurveyResponse.user))
            .filter(
                SurveyResponse.campaign_id == campaign.id,
                SurveyResponse.is_deleted == False,
                SurveyResponse.status == "SUBMITTED",
            )
            .order_by(SurveyResponse.submitted_at.desc())
            .all()
        )

    items: List[Dict[str, Any]] = []
    if campaign.submit_scope == "VEHICLE":
        target_vehicles = resolve_campaign_target_vehicles(campaign)
        by_vno: Dict[str, List[SurveyResponse]] = {}
        for r in responses:
            vno = (r.vehicle_no or "").strip()
            if vno:
                by_vno.setdefault(vno, []).append(r)

        completed_count = 0
        for v in target_vehicles:
            vno = v["vehicle_no"]
            rows = by_vno.get(vno, [])
            is_done = len(rows) > 0
            if is_done:
                completed_count += 1
            submitters = []
            for r in rows:
                snap = r.submitter_snapshot or {}
                submitters.append(
                    {
                        "response_id": r.id,
                        "user_id": r.user_id,
                        "name": snap.get("real_name") or snap.get("username") or (r.user.real_name if r.user else "-"),
                        "group": snap.get("primary_group") or "",
                        "submitted_at": (r.updated_at or r.submitted_at).strftime("%Y-%m-%d %H:%M")
                        if (r.updated_at or r.submitted_at)
                        else None,
                        "has_issue": bool(r.has_issue),
                    }
                )
            items.append(
                {
                    "target_key": vno,
                    "label": f"{vno}호",
                    "sub_label": v.get("route") or "",
                    "is_submitted": is_done,
                    "has_issue": any(bool(r.has_issue) for r in rows),
                    "submitters": submitters,
                }
            )

        target_count = len(target_vehicles)
        missing_count = max(0, target_count - completed_count)
        rate = round((completed_count / target_count) * 100, 1) if target_count > 0 else 0.0
        return {
            "target_scope": "VEHICLE",
            "target_count": target_count,
            "completed_count": completed_count,
            "missing_count": missing_count,
            "response_rate": rate,
            "items": items,
        }

    # USER 단위
    target_users = resolve_campaign_target_users(db, campaign)
    by_uid: Dict[int, SurveyResponse] = {}
    for r in responses:
        if r.user_id is not None and r.user_id not in by_uid:
            by_uid[r.user_id] = r

    completed_count = 0
    for u in target_users:
        r = by_uid.get(u.id)
        is_done = r is not None
        if is_done:
            completed_count += 1
        submitters = []
        if r is not None:
            snap = r.submitter_snapshot or {}
            submitters.append(
                {
                    "response_id": r.id,
                    "user_id": u.id,
                    "name": snap.get("real_name") or snap.get("username") or u.real_name or u.username,
                    "group": snap.get("primary_group") or (getattr(u.profile, "primary_group", None) if u.profile else "") or "",
                    "submitted_at": (r.updated_at or r.submitted_at).strftime("%Y-%m-%d %H:%M")
                    if (r.updated_at or r.submitted_at)
                    else None,
                    "has_issue": bool(r.has_issue),
                }
            )
        items.append(
            {
                "target_key": str(u.id),
                "label": u.real_name or u.username,
                "sub_label": getattr(u.profile, "primary_group", None) if u.profile else "",
                "is_submitted": is_done,
                "has_issue": bool(r.has_issue) if r else False,
                "submitters": submitters,
            }
        )

    target_count = len(target_users)
    missing_count = max(0, target_count - completed_count)
    rate = round((completed_count / target_count) * 100, 1) if target_count > 0 else 0.0
    return {
        "target_scope": "USER",
        "target_count": target_count,
        "completed_count": completed_count,
        "missing_count": missing_count,
        "response_rate": rate,
        "items": items,
    }


def _is_empty_answer(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def validate_and_normalize_answers(
    form_schema: List[Dict[str, Any]],
    raw_answers: Dict[str, Any],
    *,
    is_draft: bool = False,
) -> Dict[str, Any]:
    """질문 스키마 기준으로 응답을 정규화하고 필수 입력을 검증합니다."""
    normalized: Dict[str, Any] = {}
    answers = raw_answers if isinstance(raw_answers, dict) else {}

    for field in form_schema or []:
        key = field.get("key")
        if not key:
            continue
        ftype = field.get("type", "text")
        required = bool(field.get("required", False))
        label = field.get("label") or key
        val = answers.get(key)

        if ftype == "number":
            if val is not None and str(val).strip() != "":
                try:
                    num = float(val)
                    normalized[key] = int(num) if num.is_integer() else num
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"'{label}' 항목은 숫자만 입력할 수 있습니다.")
            elif not is_draft and required:
                raise HTTPException(status_code=400, detail=f"'{label}' 항목은 필수 입력입니다.")
        elif ftype == "number_group":
            sub_val = val if isinstance(val, dict) else {}
            sub_norm: Dict[str, Any] = {}
            for sub in field.get("fields") or []:
                skey = sub.get("key")
                if not skey:
                    continue
                sraw = sub_val.get(skey)
                if sraw is not None and str(sraw).strip() != "":
                    try:
                        snum = float(sraw)
                        sub_norm[skey] = int(snum) if snum.is_integer() else snum
                    except (TypeError, ValueError):
                        raise HTTPException(
                            status_code=400,
                            detail=f"'{label} - {sub.get('label') or skey}' 항목은 숫자만 입력할 수 있습니다.",
                        )
                elif not is_draft and required:
                    raise HTTPException(
                        status_code=400,
                        detail=f"'{label} - {sub.get('label') or skey}' 항목은 필수 입력입니다.",
                    )
            normalized[key] = sub_norm
        elif ftype == "checkbox":
            arr = val if isinstance(val, list) else ([] if val in (None, "") else [val])
            clean_arr = [str(v) for v in arr if str(v).strip() != ""]
            if not is_draft and required and len(clean_arr) == 0:
                raise HTTPException(status_code=400, detail=f"'{label}' 항목을 1개 이상 선택해 주세요.")
            normalized[key] = clean_arr
        elif ftype == "photo":
            arr = val if isinstance(val, list) else ([] if val in (None, "") else [val])
            clean_arr = [str(v) for v in arr if str(v).strip() != ""]
            if not is_draft and required and len(clean_arr) == 0:
                raise HTTPException(status_code=400, detail=f"'{label}' 사진을 첨부해 주세요.")
            normalized[key] = clean_arr
        else:
            if not is_draft and required and _is_empty_answer(val):
                raise HTTPException(status_code=400, detail=f"'{label}' 항목은 필수 입력입니다.")
            if val is not None:
                normalized[key] = val.strip() if isinstance(val, str) else val

    # 스키마 외 추가 키가 있더라도 유실되지 않게 유지
    for k, v in answers.items():
        if k not in normalized and v is not None:
            normalized[k] = v

    return normalized


def evaluate_has_issue(form_schema: List[Dict[str, Any]], answers: Dict[str, Any]) -> bool:
    """issue_values에 해당하는 답변이 하나라도 포함되면 True를 반환합니다."""
    if not isinstance(answers, dict):
        return False

    for field in form_schema or []:
        key = field.get("key")
        issue_vals = field.get("issue_values") or []
        if not key or not issue_vals:
            continue
        issue_set = {str(x) for x in issue_vals}
        val = answers.get(key)
        if isinstance(val, list):
            if any(str(v) in issue_set for v in val):
                return True
        elif val is not None and str(val) in issue_set:
            return True
    return False


def upsert_response(
    db: Session,
    campaign: SurveyCampaign,
    user: User,
    *,
    vehicle_no: Optional[str],
    answers: Dict[str, Any],
    status_val: str = "SUBMITTED",
    source_app_id: str = "survey",
    source_ref_id: Optional[str] = None,
) -> SurveyResponse:
    """사용자 또는 차량 단위로 응답을 생성하거나 수정 저장합니다."""
    if campaign.status != "OPEN":
        raise HTTPException(status_code=400, detail="현재 진행 중(OPEN)인 조사가 아니므로 제출할 수 없습니다.")

    options = campaign.options or {}
    if campaign.due_at and datetime.now() > campaign.due_at and not options.get("allow_after_due", False):
        raise HTTPException(status_code=400, detail="마감 기한이 지나 제출할 수 없습니다.")

    vno_clean: Optional[str] = None
    if campaign.submit_scope == "VEHICLE":
        vno_clean = (vehicle_no or "").strip()
        if not vno_clean:
            raise HTTPException(status_code=400, detail="차량별 조사는 차량번호를 반드시 선택해야 합니다.")
        vt = (campaign.options or {}).get("vehicle_target") if isinstance(campaign.options, dict) else None
        if isinstance(vt, dict) and str(vt.get("mode") or "ALL").upper() != "ALL":
            allowed_vnos = {v["vehicle_no"] for v in resolve_campaign_target_vehicles(campaign)}
            if vno_clean not in allowed_vnos:
                raise HTTPException(status_code=400, detail=f"차량({vno_clean})은 이 조사의 대상 차량이 아닙니다.")

    is_draft = status_val == "DRAFT"
    norm_answers = validate_and_normalize_answers(campaign.form_schema or [], answers, is_draft=is_draft)
    has_issue = evaluate_has_issue(campaign.form_schema or [], norm_answers)

    conflict_mode = resolve_campaign_conflict_mode(db, campaign)

    if campaign.submit_scope == "VEHICLE":
        if conflict_mode in ("MULTI_ADMIN_PICK", "MULTI_UNION_RESOLVE"):
            existing = (
                db.query(SurveyResponse)
                .filter(
                    SurveyResponse.campaign_id == campaign.id,
                    SurveyResponse.vehicle_no == vno_clean,
                    SurveyResponse.user_id == user.id,
                    SurveyResponse.is_deleted == False,
                )
                .first()
            )
        else:
            existing = (
                db.query(SurveyResponse)
                .filter(
                    SurveyResponse.campaign_id == campaign.id,
                    SurveyResponse.vehicle_no == vno_clean,
                    SurveyResponse.is_deleted == False,
                )
                .first()
            )
            if existing and conflict_mode == "FIRST_COME_OWNER" and existing.user_id != user.id:
                snap = existing.submitter_snapshot or {}
                owner_name = snap.get("real_name") or snap.get("username") or "다른 조사원"
                raise HTTPException(
                    status_code=403,
                    detail=f"이미 {owner_name}님이 해당 차량({vno_clean}) 조사를 완료하여 수정할 수 없습니다.",
                )
    else:
        existing = (
            db.query(SurveyResponse)
            .filter(
                SurveyResponse.campaign_id == campaign.id,
                SurveyResponse.user_id == user.id,
                SurveyResponse.vehicle_no.is_(None),
                SurveyResponse.is_deleted == False,
            )
            .first()
        )

    snapshot_user = {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "primary_group": getattr(user.profile, "primary_group", None) if user.profile else None,
        "rank_level": user.rank(),
    }

    if existing:
        if not options.get("allow_edit", True) and existing.status == "SUBMITTED":
            raise HTTPException(status_code=400, detail="이 조사는 제출 후 수정이 허용되지 않습니다.")
        existing.answers = norm_answers
        existing.has_issue = has_issue
        existing.status = status_val
        existing.schema_version = campaign.schema_version
        existing.form_snapshot = campaign.form_schema or []
        existing.submitter_snapshot = snapshot_user
        existing.source_app_id = source_app_id or existing.source_app_id
        if source_ref_id:
            existing.source_ref_id = source_ref_id
        existing.updated_at = datetime.now()
        db.commit()
        db.refresh(existing)
        return existing

    row = SurveyResponse(
        campaign_id=campaign.id,
        user_id=user.id,
        submitter_snapshot=snapshot_user,
        vehicle_no=vno_clean,
        answers=norm_answers,
        schema_version=campaign.schema_version,
        form_snapshot=campaign.form_schema or [],
        has_issue=has_issue,
        source_app_id=source_app_id or "survey",
        source_ref_id=source_ref_id,
        status=status_val,
        submitted_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_campaign_stats(db: Session, campaign: SurveyCampaign) -> Dict[str, Any]:
    """문항 타입별 통계 집계 및 미제출자/미제출 차량 목록을 생성합니다."""
    responses = (
        db.query(SurveyResponse)
        .options(joinedload(SurveyResponse.user))
        .filter(
            SurveyResponse.campaign_id == campaign.id,
            SurveyResponse.is_deleted == False,
            SurveyResponse.status == "SUBMITTED",
        )
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )

    submitted_user_ids: Set[int] = {r.user_id for r in responses if r.user_id is not None}
    submitted_count = len(responses)
    issue_count = sum(1 for r in responses if r.has_issue)

    if campaign.submit_scope == "VEHICLE":
        target_vehicles = resolve_campaign_target_vehicles(campaign)
        target_vno_set = {v["vehicle_no"] for v in target_vehicles}
        submitted_vnos = {(r.vehicle_no or "").strip() for r in responses if (r.vehicle_no or "").strip()}
        completed_target_vnos = target_vno_set & submitted_vnos
        missing_vehicles = [v for v in target_vehicles if v["vehicle_no"] not in submitted_vnos]
        missing_users: List[Dict[str, Any]] = []
        target_count = len(target_vehicles)
        submitted_target_count = len(completed_target_vnos)
        missing_count = len(missing_vehicles)
        response_rate = round((submitted_target_count / target_count) * 100, 1) if target_count > 0 else 0.0
        remind_target_count = len(resolve_campaign_target_users(db, campaign)) if missing_count > 0 else 0
    else:
        target_users = resolve_campaign_target_users(db, campaign)
        missing_vehicles = []
        missing_users = [
            {
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name or u.username,
                "primary_group": getattr(u.profile, "primary_group", None) if u.profile else None,
            }
            for u in target_users
            if u.id not in submitted_user_ids
        ]
        target_count = len(target_users)
        target_uid_set = {u.id for u in target_users}
        submitted_target_count = len(submitted_user_ids & target_uid_set)
        missing_count = len(missing_users)
        response_rate = round((submitted_target_count / target_count) * 100, 1) if target_count > 0 else 0.0
        remind_target_count = missing_count

    fields_stats: List[Dict[str, Any]] = []
    for field in campaign.form_schema or []:
        key = field.get("key")
        if not key:
            continue
        ftype = field.get("type", "text")
        label = field.get("label") or key

        if ftype in ("radio", "select", "checkbox"):
            options = list(field.get("options") or [])
            counts: Dict[str, int] = {str(opt): 0 for opt in options}
            answered = 0
            for r in responses:
                val = (r.answers or {}).get(key)
                if ftype == "checkbox":
                    arr = val if isinstance(val, list) else ([] if val is None else [val])
                    if arr:
                        answered += 1
                    for item in arr:
                        s = str(item)
                        counts[s] = counts.get(s, 0) + 1
                else:
                    if val is not None and str(val).strip() != "":
                        answered += 1
                        s = str(val)
                        counts[s] = counts.get(s, 0) + 1
            denom = submitted_count if ftype == "checkbox" else (answered or submitted_count)
            distribution = [
                {
                    "option": opt,
                    "count": cnt,
                    "ratio": round((cnt / denom) * 100, 1) if denom > 0 else 0.0,
                    "is_issue": opt in set(str(x) for x in (field.get("issue_values") or [])),
                }
                for opt, cnt in counts.items()
            ]
            fields_stats.append({
                "key": key,
                "label": label,
                "type": ftype,
                "answered_count": answered,
                "distribution": distribution,
            })
        elif ftype == "number":
            nums: List[float] = []
            for r in responses:
                val = (r.answers or {}).get(key)
                if isinstance(val, (int, float)):
                    nums.append(float(val))
            total = sum(nums)
            fields_stats.append({
                "key": key,
                "label": label,
                "type": ftype,
                "unit": field.get("unit") or "",
                "answered_count": len(nums),
                "aggregates": {
                    "sum": int(total) if float(total).is_integer() else round(total, 2),
                    "avg": round(total / len(nums), 2) if nums else 0,
                    "min": min(nums) if nums else None,
                    "max": max(nums) if nums else None,
                },
            })
        elif ftype == "number_group":
            sub_aggs: Dict[str, Any] = {}
            for sub in field.get("fields") or []:
                skey = sub.get("key")
                if not skey:
                    continue
                nums = []
                for r in responses:
                    grp = (r.answers or {}).get(key)
                    if isinstance(grp, dict) and isinstance(grp.get(skey), (int, float)):
                        nums.append(float(grp[skey]))
                total = sum(nums)
                sub_aggs[skey] = {
                    "label": sub.get("label") or skey,
                    "unit": sub.get("unit") or "",
                    "count": len(nums),
                    "sum": int(total) if float(total).is_integer() else round(total, 2),
                    "avg": round(total / len(nums), 2) if nums else 0,
                    "min": min(nums) if nums else None,
                    "max": max(nums) if nums else None,
                }
            fields_stats.append({
                "key": key,
                "label": label,
                "type": ftype,
                "aggregates": sub_aggs,
            })
        elif ftype == "photo":
            photo_rows = 0
            total_photos = 0
            for r in responses:
                val = (r.answers or {}).get(key)
                if isinstance(val, list) and len(val) > 0:
                    photo_rows += 1
                    total_photos += len(val)
            fields_stats.append({
                "key": key,
                "label": label,
                "type": ftype,
                "answered_count": photo_rows,
                "total_photos": total_photos,
            })
        else:
            samples: List[Dict[str, Any]] = []
            answered = 0
            for r in responses:
                val = (r.answers or {}).get(key)
                if not _is_empty_answer(val):
                    answered += 1
                    if len(samples) < 20:
                        snap = r.submitter_snapshot or {}
                        samples.append({
                            "submitter": snap.get("real_name") or snap.get("username") or "-",
                            "vehicle_no": r.vehicle_no,
                            "value": val,
                            "has_issue": r.has_issue,
                        })
            fields_stats.append({
                "key": key,
                "label": label,
                "type": ftype,
                "answered_count": answered,
                "samples": samples,
            })

    conflict_mode = resolve_campaign_conflict_mode(db, campaign)
    vehicle_groups = (
        build_vehicle_groups(campaign, responses, conflict_mode)
        if campaign.submit_scope == "VEHICLE"
        else []
    )

    return {
        "summary": {
            "target_scope": "VEHICLE" if campaign.submit_scope == "VEHICLE" else "USER",
            "target_count": target_count,
            "submitted_count": submitted_count,
            "submitted_target_count": submitted_target_count,
            "submitted_user_count": len(submitted_user_ids),
            "missing_count": missing_count,
            "remind_target_count": remind_target_count,
            "response_rate": response_rate,
            "issue_count": issue_count,
            "missing_users": missing_users,
            "missing_vehicles": missing_vehicles,
        },
        "conflict_mode": conflict_mode,
        "vehicle_groups": vehicle_groups,
        "fields": fields_stats,
    }


def build_campaign_csv(db: Session, campaign: SurveyCampaign) -> str:
    """캠페인 응답 원장을 UTF-8 BOM CSV 문자열로 변환합니다."""
    responses = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.campaign_id == campaign.id,
            SurveyResponse.is_deleted == False,
        )
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )

    headers = ["응답ID", "제출일시", "수정일시", "제출자", "소속그룹", "차량번호", "이상여부", "유입경로"]
    col_extractors = []

    for field in campaign.form_schema or []:
        key = field.get("key")
        if not key:
            continue
        label = field.get("label") or key
        ftype = field.get("type", "text")
        if ftype == "number_group":
            for sub in field.get("fields") or []:
                skey = sub.get("key")
                slabel = sub.get("label") or skey
                if skey:
                    headers.append(f"{label} - {slabel}")
                    col_extractors.append(("group", key, skey))
        else:
            headers.append(label)
            col_extractors.append(("flat", key, ftype))

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in responses:
        snap = r.submitter_snapshot or {}
        ans = r.answers or {}
        row = [
            r.id,
            r.submitted_at.strftime("%Y-%m-%d %H:%M") if r.submitted_at else "",
            r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else "",
            snap.get("real_name") or snap.get("username") or "",
            snap.get("primary_group") or "",
            r.vehicle_no or "",
            "이상/교체필요" if r.has_issue else "정상",
            r.source_app_id or "survey",
        ]
        for kind, key, extra in col_extractors:
            if kind == "group":
                grp = ans.get(key)
                row.append(grp.get(extra, "") if isinstance(grp, dict) else "")
            else:
                val = ans.get(key)
                if isinstance(val, list):
                    row.append(", ".join(str(x) for x in val))
                elif val is None:
                    row.append("")
                else:
                    row.append(str(val))
        writer.writerow(row)

    return output.getvalue()


SURVEY_TEMPLATES_KEY = "SURVEY_TEMPLATES"

BUILTIN_SURVEY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "builtin-extinguisher",
        "name": "차량 소화기 현황 및 스티커 점검",
        "category": "VEHICLE",
        "description": "배정 차량의 대형/소형 소화기 보유 수량과 스티커 훼손·교체 여부를 확인하여 제출해 주세요.",
        "submit_scope": "VEHICLE",
        "is_builtin": True,
        "form_schema": [
            {
                "key": "extinguisher_qty",
                "label": "차량 소화기 현황 (보유 수량)",
                "type": "number_group",
                "required": True,
                "fields": [
                    {"key": "large", "label": "대형", "unit": "개", "min": 0, "default": 1},
                    {"key": "small", "label": "소형", "unit": "개", "min": 0, "default": 1},
                ],
            },
            {
                "key": "sticker_status",
                "label": "소화기 스티커 상태",
                "type": "radio",
                "required": True,
                "options": ["모두 정상", "일부 교체 필요", "전량 교체 필요"],
                "issue_values": ["일부 교체 필요", "전량 교체 필요"],
            },
            {
                "key": "sticker_detail",
                "label": "상세 내역 (정상/교체 수량 등)",
                "type": "text",
                "required": False,
                "placeholder": "예: 2개 정상, 1개 교체요",
            },
            {
                "key": "evidence_photo",
                "label": "현장 사진 (교체 필요 시 첨부)",
                "type": "photo",
                "required": False,
                "max_files": 3,
            },
        ],
    },
    {
        "id": "builtin-uniform",
        "name": "근무복 · 안전화 지급 사이즈 조사",
        "category": "HR",
        "description": "계절별 근무복 및 안전화 신규 지급을 위해 본인 사이즈를 선택해 주세요.",
        "submit_scope": "USER",
        "is_builtin": True,
        "form_schema": [
            {
                "key": "top_size",
                "label": "상의(점퍼/조끼) 사이즈",
                "type": "radio",
                "required": True,
                "options": ["95(M)", "100(L)", "105(XL)", "110(2XL)", "115(3XL)"],
            },
            {
                "key": "bottom_size",
                "label": "하의(바지) 허리 사이즈",
                "type": "select",
                "required": True,
                "options": ["28", "30", "32", "34", "36", "38", "40"],
            },
            {
                "key": "shoe_size",
                "label": "안전화(운동화) 치수 (mm)",
                "type": "number",
                "unit": "mm",
                "required": True,
                "default": 265,
            },
            {
                "key": "extra_note",
                "label": "특이사항 (수선/추가 요청)",
                "type": "text",
                "required": False,
                "placeholder": "필요 시 입력",
            },
        ],
    },
    {
        "id": "builtin-safety-check",
        "name": "차량 안전장비 · 비품 정기 점검",
        "category": "SAFETY",
        "description": "비상망치, 구급함, 삼각대, 블랙박스 작동 상태를 점검해 주세요.",
        "submit_scope": "VEHICLE",
        "is_builtin": True,
        "form_schema": [
            {
                "key": "missing_items",
                "label": "점검 결과 누락·불량 항목",
                "type": "checkbox",
                "required": False,
                "options": ["모두 정상", "비상망치", "구급함", "안전삼각대", "후방카메라/블랙박스"],
                "issue_values": ["비상망치", "구급함", "안전삼각대", "후방카메라/블랙박스"],
            },
            {
                "key": "overall_state",
                "label": "종합 판정",
                "type": "radio",
                "required": True,
                "options": ["정상 운행", "보완 필요"],
                "issue_values": ["보완 필요"],
            },
            {
                "key": "note",
                "label": "조치 요청 사항",
                "type": "textarea",
                "required": False,
                "placeholder": "교체 또는 보충이 필요한 품목과 수량을 적어주세요",
            },
        ],
    },
]


def _load_custom_templates(db: Session) -> List[Dict[str, Any]]:
    from models import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == SURVEY_TEMPLATES_KEY).first()
    if row and isinstance(row.value, list):
        return [dict(item) for item in row.value if isinstance(item, dict) and item.get("id")]
    return []


def _persist_custom_templates(db: Session, items: List[Dict[str, Any]]) -> None:
    from models import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == SURVEY_TEMPLATES_KEY).first()
    if row:
        row.value = items
    else:
        db.add(
            SystemConfig(
                key=SURVEY_TEMPLATES_KEY,
                value=items,
                description="관리자 현장 조사·설문 재사용 템플릿 목록",
            )
        )
    db.commit()


def list_survey_templates(db: Session) -> List[Dict[str, Any]]:
    custom = _load_custom_templates(db)
    return [*custom, *BUILTIN_SURVEY_TEMPLATES]


def save_survey_template(db: Session, payload: Dict[str, Any], user: Optional[User] = None) -> Dict[str, Any]:
    custom = _load_custom_templates(db)
    tpl_id = (payload.get("id") or "").strip()
    if not tpl_id or tpl_id.startswith("builtin-"):
        tpl_id = f"tpl-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"

    entry = {
        "id": tpl_id,
        "name": str(payload.get("name") or "").strip(),
        "category": payload.get("category") or "GENERAL",
        "description": payload.get("description") or "",
        "submit_scope": payload.get("submit_scope") or "USER",
        "form_schema": payload.get("form_schema") or [],
        "is_builtin": False,
        "created_by": getattr(user, "real_name", None) or getattr(user, "username", None) or "admin",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    updated = False
    for idx, item in enumerate(custom):
        if item.get("id") == tpl_id:
            custom[idx] = entry
            updated = True
            break
    if not updated:
        custom.insert(0, entry)

    _persist_custom_templates(db, custom)
    return entry


def delete_survey_template(db: Session, template_id: str) -> None:
    if template_id.startswith("builtin-"):
        raise HTTPException(status_code=400, detail="기본 내장 템플릿은 삭제할 수 없습니다.")
    custom = _load_custom_templates(db)
    filtered = [item for item in custom if item.get("id") != template_id]
    if len(filtered) == len(custom):
        raise HTTPException(status_code=404, detail="삭제할 템플릿을 찾을 수 없습니다.")
    _persist_custom_templates(db, filtered)


SURVEY_SETTINGS_KEY = "survey_settings"

TARGET_CONFLICT_MODES = (
    "FIRST_COME_OWNER",
    "FIRST_COME_SHARED",
    "MULTI_ADMIN_PICK",
    "MULTI_UNION_RESOLVE",
)

DEFAULT_SURVEY_SETTINGS: Dict[str, Any] = {
    "default_category": "GENERAL",
    "default_submit_scope": "USER",
    "default_allow_edit": True,
    "default_push_on_open": True,
    "default_max_photos": 3,
    "allow_untargeted_admin_submit": True,
    "target_conflict_mode": "FIRST_COME_OWNER",
}


def get_survey_settings(db: Session) -> Dict[str, Any]:
    """조사·설문 앱 전역 비즈니스 설정을 SystemConfig에서 조회합니다."""
    row = db.query(SystemConfig).filter(SystemConfig.key == SURVEY_SETTINGS_KEY).first()
    raw = row.value if row and isinstance(row.value, dict) else {}
    merged = {**DEFAULT_SURVEY_SETTINGS, **raw}
    merged["default_max_photos"] = max(1, min(10, int(merged.get("default_max_photos") or 3)))
    if merged.get("target_conflict_mode") not in TARGET_CONFLICT_MODES:
        merged["target_conflict_mode"] = "FIRST_COME_OWNER"
    return merged


def save_survey_settings(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """조사·설문 앱 전역 비즈니스 설정을 SystemConfig에 저장합니다."""
    mode = str(payload.get("target_conflict_mode") or "FIRST_COME_OWNER")
    if mode not in TARGET_CONFLICT_MODES:
        mode = "FIRST_COME_OWNER"
    clean = {
        "default_category": str(payload.get("default_category") or "GENERAL"),
        "default_submit_scope": "VEHICLE" if payload.get("default_submit_scope") == "VEHICLE" else "USER",
        "default_allow_edit": bool(payload.get("default_allow_edit", True)),
        "default_push_on_open": bool(payload.get("default_push_on_open", True)),
        "default_max_photos": max(1, min(10, int(payload.get("default_max_photos") or 3))),
        "allow_untargeted_admin_submit": bool(payload.get("allow_untargeted_admin_submit", True)),
        "target_conflict_mode": mode,
    }
    row = db.query(SystemConfig).filter(SystemConfig.key == SURVEY_SETTINGS_KEY).first()
    if row:
        row.value = clean
    else:
        db.add(
            SystemConfig(
                key=SURVEY_SETTINGS_KEY,
                value=clean,
                description="현장 조사·설문 앱 전역 비즈니스 설정",
            )
        )
    db.commit()
    return clean


def resolve_campaign_conflict_mode(db: Session, campaign: SurveyCampaign) -> str:
    """캠페인별 예외 설정이 있으면 우선 적용하고, 없으면 전역 설정값을 따릅니다."""
    opts = campaign.options if isinstance(campaign.options, dict) else {}
    override = opts.get("target_conflict_mode")
    if override in TARGET_CONFLICT_MODES:
        return str(override)
    return str(get_survey_settings(db).get("target_conflict_mode", "FIRST_COME_OWNER"))


def _canonical_val(val: Any) -> str:
    try:
        return json.dumps(val, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(val)


def build_vehicle_groups(
    campaign: SurveyCampaign,
    responses: List[SurveyResponse],
    conflict_mode: str,
) -> List[Dict[str, Any]]:
    """차량별 응답을 그룹화하고, 복수 작성 시 공통 합의 문항과 이견 문항을 분리합니다."""
    grouped: Dict[str, List[SurveyResponse]] = {}
    for r in responses:
        vno = (r.vehicle_no or "").strip()
        if not vno:
            continue
        grouped.setdefault(vno, []).append(r)

    resolutions = (campaign.options or {}).get("vehicle_resolutions") or {}
    schema_fields = campaign.form_schema or []
    result: List[Dict[str, Any]] = []

    for vno, rows in sorted(grouped.items(), key=lambda x: x[0]):
        submissions = [serialize_response(r) for r in rows]
        agreed_answers: Dict[str, Any] = {}
        conflict_fields: List[Dict[str, Any]] = []

        if len(rows) >= 2:
            for field in schema_fields:
                key = field.get("key")
                if not key:
                    continue
                label = field.get("label") or key
                candidates = []
                distinct_vals: set[str] = set()
                for sub in submissions:
                    val = (sub.get("answers") or {}).get(key)
                    distinct_vals.add(_canonical_val(val))
                    candidates.append(
                        {
                            "response_id": sub["id"],
                            "submitter_name": sub["submitter_name"],
                            "value": val,
                        }
                    )
                if len(distinct_vals) <= 1:
                    agreed_answers[key] = candidates[0]["value"] if candidates else None
                else:
                    conflict_fields.append(
                        {
                            "key": key,
                            "label": label,
                            "candidates": candidates,
                        }
                    )

        result.append(
            {
                "vehicle_no": vno,
                "count": len(submissions),
                "conflict_mode": conflict_mode,
                "submissions": submissions,
                "agreed_answers": agreed_answers,
                "conflict_fields": conflict_fields,
                "resolution": resolutions.get(vno) if isinstance(resolutions, dict) else None,
            }
        )

    return result


def resolve_vehicle_responses(
    db: Session,
    campaign: SurveyCampaign,
    admin: User,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """관리자가 차량별 복수 응답에 대해 1건 채택(PICK) 또는 이견 문항 선택(UNION)을 확정합니다."""
    vno = str(payload.get("vehicle_no") or "").strip()
    if not vno:
        raise HTTPException(status_code=400, detail="대상 차량번호가 필요합니다.")

    mode = str(payload.get("mode") or "PICK").upper()
    opts = dict(campaign.options or {})
    resolutions = dict(opts.get("vehicle_resolutions") or {})

    if mode == "RESET":
        resolutions.pop(vno, None)
        opts["vehicle_resolutions"] = resolutions
        campaign.options = opts
        flag_modified(campaign, "options")
        db.commit()
        return {"message": f"{vno}호 차량 확정 상태가 초기화되었습니다.", "resolution": None}

    rows = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.campaign_id == campaign.id,
            SurveyResponse.vehicle_no == vno,
            SurveyResponse.is_deleted == False,
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="해당 차량의 제출 응답이 없습니다.")

    admin_name = getattr(admin, "real_name", None) or getattr(admin, "username", None) or "관리자"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if mode == "PICK":
        selected_id = payload.get("selected_response_id")
        picked = next((r for r in rows if r.id == selected_id), None)
        if not picked:
            raise HTTPException(status_code=400, detail="채택할 응답을 찾을 수 없습니다.")
        snap = picked.submitter_snapshot or {}
        entry = {
            "mode": "PICK",
            "selected_response_id": picked.id,
            "selected_submitter": snap.get("real_name") or snap.get("username") or "-",
            "resolved_answers": picked.answers or {},
            "resolved_by": admin_name,
            "resolved_at": now_str,
        }
    elif mode == "UNION":
        # 공통 합의 문항은 자동 병합하고, 이견 문항은 관리자 선택값으로 덮어씀
        groups = build_vehicle_groups(campaign, rows, "MULTI_UNION_RESOLVE")
        agreed = groups[0]["agreed_answers"] if groups else {}
        chosen = payload.get("resolved_answers") or {}
        final_answers = {**agreed, **(chosen if isinstance(chosen, dict) else {})}
        entry = {
            "mode": "UNION",
            "selected_response_id": None,
            "resolved_answers": final_answers,
            "resolved_by": admin_name,
            "resolved_at": now_str,
        }
    else:
        raise HTTPException(status_code=400, detail="지원하지 않는 확정 모드입니다.")

    resolutions[vno] = entry
    opts["vehicle_resolutions"] = resolutions
    campaign.options = opts
    flag_modified(campaign, "options")
    db.commit()
    return {"message": f"{vno}호 차량 최종 응답이 확정되었습니다.", "resolution": entry}
