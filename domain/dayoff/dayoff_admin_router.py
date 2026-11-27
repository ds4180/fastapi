"""
[결근·휴무 관리자 라우터 (domain/dayoff/dayoff_admin_router.py)]
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from core.audit import safe_log_audit
from core.deps import require_app_permission
from domain.dayoff.dayoff_policy_service import (
    delete_dayoff_policy_row,
    get_all_dayoff_policies,
    get_date_overrides,
    get_dayoff_policy,
    get_monthly_quota_status,
    get_reserved_dayoff_policy,
    is_fcfs_user,
    policy_row_to_dict,
    resolve_policy_for_date,
    save_dayoff_policy,
    update_date_overrides,
)
from domain.dayoff.dayoff_schema import DayOffDateOverrideReq, DayOffPolicySchema, DayOffStatus
from models import DayOff, User, UserProfile

router = APIRouter(tags=["Admin Dayoff"])

check_dayoff_admin = require_app_permission("dayoff", action="read")
check_dayoff_admin_write = require_app_permission("dayoff", action="write")


@router.get("/dayoffs")
def admin_get_all_dayoffs(db: Session = Depends(get_db), admin: User = Depends(check_dayoff_admin)):
    """모든 사용자의 휴무 신청 내역 조회 (관리자용 - 신청 일자 기준 유효 정책 판별)"""
    policy_rows = get_all_dayoff_policies(db)
    dayoffs = (
        db.query(DayOff)
        .join(User)
        .options(joinedload(DayOff.user).joinedload(User.profile))
        .filter(DayOff.is_deleted == False)
        .order_by(DayOff.date.desc())
        .all()
    )

    result = []
    for d in dayoffs:
        u = d.user
        day_policy = resolve_policy_for_date(policy_rows, d.date)
        fcfs = is_fcfs_user(u, day_policy) if u else False
        result.append(
            {
                "id": d.id,
                "user_id": d.user_id,
                "username": u.username if u else "unknown",
                "real_name": u.real_name if u else None,
                "primary_group": u.primary_group if u else None,
                "rank_level": u.rank() if u else 0,
                "work_type": "FCFS" if fcfs else "APPROVAL",
                "date": str(d.date),
                "type": d.type,
                "status": d.status,
                "memo": d.memo,
                "group_id": d.group_id,
                "create_date": d.create_date,
            }
        )
    return result


@router.put("/dayoffs/{dayoff_id}/status")
def admin_update_dayoff_status(
    dayoff_id: int,
    status_update: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dayoff_admin_write),
):
    """휴무 신청 상태 변경 (승인/반려 등 - 허용 상태값 검증·감사로그·알림 토글 연동)"""
    raw_status = str(status_update.get("status") or "").strip().upper()
    valid_statuses = {s.value for s in DayOffStatus}
    if raw_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 휴무 상태값입니다: '{raw_status}' (허용: {', '.join(sorted(valid_statuses))})",
        )
    new_status = raw_status

    db_dayoff = (
        db.query(DayOff)
        .filter(DayOff.id == dayoff_id, DayOff.is_deleted == False)
        .first()
    )
    if not db_dayoff:
        raise HTTPException(status_code=404, detail="내역을 찾을 수 없습니다.")

    old_status = db_dayoff.status
    affected_count = 1

    if db_dayoff.group_id:
        items = (
            db.query(DayOff)
            .filter(
                DayOff.group_id == db_dayoff.group_id,
                DayOff.user_id == db_dayoff.user_id,
                DayOff.is_deleted == False,
            )
            .all()
        )
        affected_count = len(items)
        for item in items:
            item.status = new_status
    else:
        db_dayoff.status = new_status

    db.commit()

    safe_log_audit(
        db=db,
        app_id="dayoff",
        log_type="CHANGE",
        action="DAYOFF_STATUS_UPDATE",
        title=f"휴무 신청 상태 변경 (#{dayoff_id}: {old_status} → {new_status})",
        user=admin,
        resource_type="dayoff",
        resource_id=str(dayoff_id),
        message=f"관리자 '{admin.username}'이(가) 사원(#{db_dayoff.user_id})의 {db_dayoff.date} 휴무 {affected_count}건을 {new_status}(으)로 처리했습니다.",
        diff_payload=[{"field": "status", "from": old_status, "to": new_status}],
    )

    if new_status in ("APPROVED", "REJECTED"):
        try:
            today_policy = get_dayoff_policy(db)
            etc_cfg = today_policy.get("etc") if isinstance(today_policy.get("etc"), dict) else {}
            notify_result_enabled = etc_cfg.get("notify_on_result", True) is not False

            if notify_result_enabled:
                from core.notify import safe_notify
                from domain.push.push_service import is_push_domain_enabled

                status_label = "승인" if new_status == "APPROVED" else "반려"
                date_label = str(db_dayoff.date) if getattr(db_dayoff, "date", None) else "신청일"
                safe_notify(
                    db=db,
                    category="NOTIFICATION",
                    title=f"휴무 신청이 {status_label}되었습니다",
                    message=f"{date_label} 휴무 신청 건이 {status_label} 처리되었습니다.",
                    sender=admin,
                    target_user_ids=[db_dayoff.user_id],
                    level=2 if new_status == "APPROVED" else 3,
                    link="/v1/custom/dayoff",
                    extra_payload={"send_web_push": is_push_domain_enabled(db, "dayoff_result")},
                )
        except Exception:
            pass

    return {"message": "success", "new_status": new_status}


@router.get("/dayoff-policy")
def admin_get_dayoff_policy(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dayoff_admin),
):
    """결근/휴무 정책 이력, 기준일 유효 정책 및 월간 일별 정원 현황 조회"""
    now = datetime.now()
    y = year if year and 1970 <= year <= 2100 else now.year
    m = month if month and 1 <= month <= 12 else now.month

    policy_rows = get_all_dayoff_policies(db)
    policies = [policy_row_to_dict(r) for r in policy_rows]
    monthly = get_monthly_quota_status(db, y, m, admin)
    today_policy = get_dayoff_policy(db, now.date())
    reserved_policy = get_reserved_dayoff_policy(db, now.date())
    date_overrides = get_date_overrides(db)

    group_codes = set(["운전직", "운수팀", "사무직", "관리팀"])
    for g in db.query(models.Group.code).all():
        if g[0]:
            group_codes.add(str(g[0]).strip())
    for p in db.query(UserProfile.primary_group).distinct().all():
        if p[0]:
            group_codes.add(str(p[0]).strip())
    for row_dict in policies:
        for fg in row_dict.get("fcfs_groups", []):
            if fg:
                group_codes.add(str(fg).strip())

    return {
        "policy": today_policy,
        "today_policy": today_policy,
        "reserved_policy": reserved_policy,
        "date_overrides": date_overrides,
        "available_groups": sorted(list(group_codes)),
        "monthly_quota": monthly,
    }


@router.put("/dayoff-policy")
def admin_update_dayoff_policy(
    payload: DayOffPolicySchema,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dayoff_admin_write),
):
    """Append-Only: 적용날짜 기준 새 결근/휴무 정책 레코드를 추가(INSERT)합니다."""
    eff_date = payload.effective_date or datetime.now().date()
    old_policy = get_dayoff_policy(db, as_of=eff_date)
    saved = save_dayoff_policy(db, payload.model_dump(exclude_none=True))

    win_desc = (
        f"D+{saved['min_advance_days']}~D+{saved['max_advance_days']}"
        if saved.get("max_advance_days", 0) > 0
        else f"D+{saved['min_advance_days']}~무제한"
    )
    safe_log_audit(
        db=db,
        app_id="dayoff",
        log_type="SYSTEM",
        action="DAYOFF_POLICY_APPENDED",
        title=f"결근/휴무 정책 추가 (적용일: {saved['effective_date']})",
        user=admin,
        resource_type="dayoff_policy",
        resource_id=str(saved["id"]),
        message=f"관리자 '{admin.username}'이(가) {saved['effective_date']}부터 적용되는 휴무 정책(#{saved['id']})을 등록했습니다. (정원: {saved['daily_quota']}명, 월최대: {saved['max_monthly_count']}회, 1회최대: {saved['max_days_per_request']}일, 신청기간: {win_desc})",
        diff_payload=[{"field": "dayoff_policy", "from": old_policy, "to": saved}],
    )
    return {"message": "success", "policy": saved}


@router.put("/dayoff-policy/date-override")
def admin_update_dayoff_date_override(
    payload: DayOffDateOverrideReq,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dayoff_admin_write),
):
    """특정 날짜(단일 또는 복수 일자)의 선착순 예외 정원을 정책 이력과 분리하여 저장합니다."""
    saved_overrides = update_date_overrides(db, payload.dates, payload.quota)
    return {"message": "success", "date_overrides": saved_overrides}


@router.delete("/dayoff-policy/{policy_id}")
def admin_delete_dayoff_policy_row(
    policy_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dayoff_admin_write),
):
    """특정 정책 레코드(#id)를 논리 삭제합니다."""
    delete_dayoff_policy_row(db, policy_id)

    safe_log_audit(
        db=db,
        app_id="dayoff",
        log_type="SYSTEM",
        action="DAYOFF_POLICY_DELETED",
        title=f"결근/휴무 정책 #{policy_id} 삭제",
        user=admin,
        resource_type="dayoff_policy",
        resource_id=str(policy_id),
        message=f"관리자 '{admin.username}'이(가) 정책 레코드 #{policy_id}를 삭제했습니다.",
    )
    return {"message": "success", "deleted_id": policy_id}
