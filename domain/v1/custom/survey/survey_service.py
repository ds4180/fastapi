"""
============================================================================
[현장 조사·설문 비즈니스 로직 & 통계 엔진 (domain/v1/custom/survey/survey_service.py)]
============================================================================
"""

from __future__ import annotations
import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import SurveyCampaign, SurveyResponse, User
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
            from domain.v1.admin.admin_router import load_drivers_metadata
            _, vehicle_map, _ = load_drivers_metadata()
            for candidate in (getattr(user, "real_name", None), getattr(user, "username", None)):
                if candidate and candidate.strip() in vehicle_map:
                    default_vehicle = vehicle_map[candidate.strip()]
                    break
        except Exception:
            default_vehicle = None

    return {
        "vehicles": vehicles,
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

    is_draft = status_val == "DRAFT"
    norm_answers = validate_and_normalize_answers(campaign.form_schema or [], answers, is_draft=is_draft)
    has_issue = evaluate_has_issue(campaign.form_schema or [], norm_answers)

    if campaign.submit_scope == "VEHICLE":
        existing = (
            db.query(SurveyResponse)
            .filter(
                SurveyResponse.campaign_id == campaign.id,
                SurveyResponse.vehicle_no == vno_clean,
                SurveyResponse.is_deleted == False,
            )
            .first()
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
    """문항 타입별 통계 집계 및 미제출자 목록을 생성합니다."""
    target_users = resolve_campaign_target_users(db, campaign)
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
    submitted_count = len(responses)
    if campaign.submit_scope == "USER":
        rate_base = min(len(submitted_user_ids), target_count) if target_count > 0 else 0
    else:
        rate_base = len({u_id for u_id in submitted_user_ids if any(t.id == u_id for t in target_users)})
    response_rate = round((rate_base / target_count) * 100, 1) if target_count > 0 else 0.0
    issue_count = sum(1 for r in responses if r.has_issue)

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

    return {
        "summary": {
            "target_count": target_count,
            "submitted_count": submitted_count,
            "submitted_user_count": len(submitted_user_ids),
            "missing_count": len(missing_users),
            "response_rate": response_rate,
            "issue_count": issue_count,
            "missing_users": missing_users,
        },
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
