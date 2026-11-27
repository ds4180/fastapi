"""
============================================================================
[결근/휴무 신청 CRUD (domain/dayoff/dayoff_crud.py)]
============================================================================

💡 역할:
- 사용자 결근/휴무 신청 생성, 목록 조회, 취소(Soft Delete)
- 정책·정원 엔진은 `domain.dayoff.dayoff_policy_service`로 분리되었으며,
  기존 호출부·테스트 하위 호환을 위해 주요 심볼을 재노출(re-export)합니다.
"""

from datetime import datetime, date
from typing import Dict, List
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, text

from models import DayOff, User
from domain.dayoff.dayoff_schema import DayOffCreate, DayOffStatus
from domain.dayoff.dayoff_policy_service import (
    DAYOFF_POLICY_KEY,
    DAYOFF_DATE_OVERRIDES_KEY,
    INITIAL_EFFECTIVE_DATE,
    DEFAULT_DAYOFF_POLICY,
    normalize_policy,
    compute_request_window,
    policy_row_to_dict,
    ensure_initial_dayoff_policy,
    get_all_dayoff_policies,
    resolve_policy_for_date,
    get_dayoff_policy,
    get_reserved_dayoff_policy,
    get_date_overrides,
    save_dayoff_policy,
    delete_dayoff_policy_row,
    update_date_overrides,
    get_user_rank_val,
    is_fcfs_user,
    get_quota_for_date,
    get_user_monthly_request_count,
    get_fcfs_approved_count_for_date,
    get_monthly_quota_status,
)


def create_dayoff_list(db: Session, dayoff_create: DayOffCreate, user_id: int):
    if not dayoff_create.dates:
        return 0

    user = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")

    policy_rows = get_all_dayoff_policies(db)
    date_overrides = get_date_overrides(db)
    sorted_dates = sorted(list(set(dayoff_create.dates)))
    start_str = sorted_dates[0].strftime('%Y%m%d')
    end_str = sorted_dates[-1].strftime('%Y%m%d')
    group_id = f"{start_str}-{end_str}"

    # 0. 사용자 운영 방식(자동승인 FCFS vs 허가제 APPROVAL) 판별
    # 💡 자동승인(운전직 선착순) 대상자에게만 날짜 제한(D+X ~ D+Y), 1회 최대 일수, 월 최대 횟수, 일일 정원을 적용하고,
    #    허가제(사무직 승인제) 대상자는 관리자 검토를 거치므로 날짜/횟수 제한 없이 자유 신청을 허용합니다.
    today = date.today()
    today_policy = resolve_policy_for_date(policy_rows, today)
    req_policy = resolve_policy_for_date(policy_rows, sorted_dates[0])
    is_fcfs_applicant = is_fcfs_user(user, req_policy)

    max_days = int(req_policy.get("max_days_per_request") or 0) if is_fcfs_applicant else 0
    if is_fcfs_applicant:
        req_window = compute_request_window(today_policy, today)
        min_adv = req_window["min_advance_days"]
        max_adv = req_window["max_advance_days"]

        for date_item in sorted_dates:
            days_ahead = (date_item - today).days
            if days_ahead < min_adv:
                raise HTTPException(
                    status_code=400,
                    detail=f"{date_item}은(는) 자동승인 신청 가능 최소일(오늘 기준 D+{min_adv}일, {req_window['min_date']}부터) 이전이라 신청할 수 없습니다."
                )
            if max_adv > 0 and days_ahead > max_adv:
                raise HTTPException(
                    status_code=400,
                    detail=f"{date_item}은(는) 자동승인 신청 가능 최대일(오늘 기준 D+{max_adv}일, {req_window['max_date']}까지)을 초과하여 신청할 수 없습니다."
                )

        if max_days > 0 and len(sorted_dates) > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"1회 결근계 최대 신청 일수({max_days}일)를 초과할 수 없습니다. (선택: {len(sorted_dates)}일)"
            )

    # 🔒 [동시성 제어] PostgreSQL 환경에서는 신청 일자(오름차순)별로 트랜잭션 단위 Advisory Lock을 획득하여
    #    동시 클릭 시 선착순(FCFS) 정원 초과(TOCTOU Race Condition) 및 데드락을 원천 차단합니다.
    if db.bind and db.bind.dialect.name == "postgresql":
        for lock_date in sorted_dates:
            lock_key = f"dayoff_fcfs_{lock_date.isoformat()}"
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

    # 1. 본인 중복 신청 검사 및 일자별 정책 기준 선착순 정원 검사
    target_Dates_to_insert: List[tuple] = []
    for date_item in sorted_dates:
        existing_dayoff = db.query(DayOff).filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.date == date_item,
                DayOff.is_deleted == False,
                DayOff.status.in_([DayOffStatus.REQUESTED.value, DayOffStatus.APPROVED.value])
            )
        ).first()

        if existing_dayoff:
            continue

        day_policy = resolve_policy_for_date(policy_rows, date_item)
        fcfs_mode = is_fcfs_user(user, day_policy)

        if fcfs_mode:
            d_str = date_item.strftime('%Y-%m-%d')
            quota = get_quota_for_date(d_str, day_policy, date_overrides)
            current_cnt = get_fcfs_approved_count_for_date(db, date_item, day_policy)
            if current_cnt >= quota:
                raise HTTPException(
                    status_code=409,
                    detail=f"{d_str} 일자는 운전직 선착순 휴무 정원({current_cnt}/{quota}명)이 마감되어 신청할 수 없습니다."
                )

        target_Dates_to_insert.append((date_item, fcfs_mode))

    if not target_Dates_to_insert:
        raise HTTPException(status_code=409, detail="선택하신 날짜는 이미 휴무가 신청되어 있습니다.")

    # 1-2. 자동승인(선착순) 전용: 1회 신청 일수 재확인 & 월별 최대 사용 횟수 검사
    if is_fcfs_applicant:
        if max_days > 0 and len(target_Dates_to_insert) > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"1회 결근계 최대 신청 일수({max_days}일)를 초과할 수 없습니다."
            )

        dates_by_month: Dict[tuple, List[date]] = {}
        for d_item, _ in target_Dates_to_insert:
            dates_by_month.setdefault((d_item.year, d_item.month), []).append(d_item)

        for (y, m), m_dates in dates_by_month.items():
            m_policy = resolve_policy_for_date(policy_rows, m_dates[0])
            max_monthly = int(m_policy.get("max_monthly_count") or 0)
            if max_monthly > 0:
                used_cnt = get_user_monthly_request_count(db, user_id, y, m)
                if used_cnt >= max_monthly:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{y}년 {m}월 결근계 최대 사용 횟수({max_monthly}회)를 모두 사용했습니다. (현재 {used_cnt}회)"
                    )

    # 2. 운전직(선착순)은 즉시 APPROVED 확정, 사무직(승인제)은 REQUESTED 대기로 저장
    created_count = 0
    for date_item, fcfs_mode in target_Dates_to_insert:
        initial_status = DayOffStatus.APPROVED.value if fcfs_mode else DayOffStatus.REQUESTED.value
        # 반려/취소된 동일 날짜 소프트 레코드가 남아있다면 정리 후 생성 (유니크 인덱스 보호)
        stale_dayoffs = db.query(DayOff).filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.date == date_item,
                DayOff.is_deleted == False,
                DayOff.status.in_([DayOffStatus.REJECTED.value, DayOffStatus.CANCELLED.value])
            )
        ).all()
        now_dt = datetime.now()
        for stale in stale_dayoffs:
            stale.is_deleted = True
            stale.delete_date = now_dt

        db_dayoff = DayOff(
            date=date_item,
            user_id=user_id,
            type=dayoff_create.type.value,
            status=initial_status,
            memo=dayoff_create.memo,
            group_id=group_id,
            create_date=now_dt,
            is_deleted=False
        )
        db.add(db_dayoff)
        created_count += 1

    db.commit()
    return created_count


def get_dayoff_list(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    """
    group_id별로 그룹화하여 목록을 조회합니다.
    """
    query = db.query(
        DayOff.group_id,
        DayOff.type,
        DayOff.status,
        DayOff.memo,
        func.min(DayOff.date).label('start_date'),
        func.max(DayOff.date).label('end_date'),
        func.count(DayOff.id).label('total_days'),
        func.max(DayOff.create_date).label('create_date'),
        func.min(DayOff.id).label('representative_id')
    ).filter(
        and_(DayOff.user_id == user_id, DayOff.is_deleted == False)
    ).group_by(
        DayOff.group_id, DayOff.type, DayOff.status, DayOff.memo
    ).order_by(
        func.min(DayOff.date).desc()
    )

    results = query.offset(skip).limit(limit).all()
    total_groups = db.query(func.count(func.distinct(DayOff.group_id))).filter(
        and_(DayOff.user_id == user_id, DayOff.is_deleted == False)
    ).scalar()

    formatted_list = []
    for r in results:
        date_display = f"{r.start_date}"
        if r.start_date != r.end_date:
            date_display = f"{r.start_date} ~ {r.end_date} ({r.total_days}일)"

        formatted_list.append({
            "id": r.representative_id,
            "date": date_display,
            "start_date": str(r.start_date),
            "end_date": str(r.end_date),
            "total_days": r.total_days,
            "type": r.type,
            "status": r.status,
            "memo": r.memo,
            "group_id": r.group_id,
            "create_date": r.create_date,
            "user_id": user_id
        })

    return formatted_list, total_groups


def delete_dayoff(db: Session, dayoff_id: int, user_id: int):
    db_dayoff = db.query(DayOff).filter(DayOff.id == dayoff_id).first()
    if not db_dayoff or db_dayoff.user_id != user_id:
        return False

    now = datetime.now()
    today = now.date()

    if db_dayoff.group_id:
        group_items = db.query(DayOff).filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.group_id == db_dayoff.group_id,
                DayOff.is_deleted == False
            )
        ).all()
        # 이미 승인된 건이라도 시작일이 오늘 이후(미래)인 선착순/예정 휴무는 취소 허용
        if any(item.status == DayOffStatus.APPROVED.value and item.date < today for item in group_items):
            return False
        for item in group_items:
            item.is_deleted = True
            item.delete_date = now
    else:
        if db_dayoff.status == DayOffStatus.APPROVED.value and db_dayoff.date < today:
            return False
        db_dayoff.is_deleted = True
        db_dayoff.delete_date = now

    db.commit()
    return True


__all__ = [
    "DAYOFF_POLICY_KEY",
    "DAYOFF_DATE_OVERRIDES_KEY",
    "INITIAL_EFFECTIVE_DATE",
    "DEFAULT_DAYOFF_POLICY",
    "normalize_policy",
    "compute_request_window",
    "policy_row_to_dict",
    "ensure_initial_dayoff_policy",
    "get_all_dayoff_policies",
    "resolve_policy_for_date",
    "get_dayoff_policy",
    "get_reserved_dayoff_policy",
    "get_date_overrides",
    "save_dayoff_policy",
    "delete_dayoff_policy_row",
    "update_date_overrides",
    "get_user_rank_val",
    "is_fcfs_user",
    "get_quota_for_date",
    "get_user_monthly_request_count",
    "get_fcfs_approved_count_for_date",
    "get_monthly_quota_status",
    "create_dayoff_list",
    "get_dayoff_list",
    "delete_dayoff",
]
