"""
[일정 관리 비즈니스 서비스 (domain/v1/schedule/schedule_service.py)]

💡 역할:
- 일정 생성/수정/삭제 권한 검증 (개인: Rank 0+, 공휴일·사무실·전사 일정: Tier 2 / Rank 2+)
- 반복 일정(DAILY/WEEKLY/MONTHLY/YEARLY) 기간 내 인스턴스 전개
- 본인 결근계(DayOff) + Tier 2(Rank 2+) 전용 사무실 직원 전체 결근계 병합 조회
"""

import calendar
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from models import Schedule, DayOff, User
from domain.dayoff.dayoff_policy_service import (
    get_dayoff_policy,
    get_user_rank_val,
    is_fcfs_user,
)
from domain.dayoff.dayoff_schema import DayOffStatus

DAY_CODE_TO_WEEKDAY = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}

DAYOFF_TYPE_LABELS = {
    "ANNUAL": "연차",
    "SICK": "병가",
    "SPECIAL": "경조사",
    "OFFICIAL": "공가",
}


def derive_scope(category: str) -> str:
    cat = (category or "PERSONAL").upper()
    if cat in ("GLOBAL", "HOLIDAY"):
        return "GLOBAL"
    if cat == "OFFICE":
        return "OFFICE"
    return "PERSONAL"


def _add_months(dt: datetime, months: int, target_day: Optional[int] = None) -> datetime:
    total_months = (dt.year * 12 + (dt.month - 1)) + months
    ny = total_months // 12
    nm = (total_months % 12) + 1
    last_day = calendar.monthrange(ny, nm)[1]
    nd = min(target_day or dt.day, last_day)
    return dt.replace(year=ny, month=nm, day=nd)


def _expand_schedule_occurrences(
    s: Schedule,
    win_start: date,
    win_end: date,
) -> List[Dict[str, Any]]:
    rule = s.recurrence_rule if isinstance(s.recurrence_rule, dict) else {}
    freq = str(rule.get("freq") or "NONE").upper()
    interval = max(1, int(rule.get("interval") or 1))
    by_day = [str(d).upper() for d in (rule.get("byDay") or []) if str(d).upper() in DAY_CODE_TO_WEEKDAY]
    by_month_day = rule.get("byMonthDay")
    count_limit = int(rule["count"]) if rule.get("count") else None
    until_date = None
    if rule.get("until"):
        try:
            until_date = date.fromisoformat(str(rule["until"])[:10])
        except ValueError:
            until_date = None

    base_start = s.start_at
    base_end = s.end_at if (s.end_at and s.end_at >= base_start) else base_start
    duration = base_end - base_start

    occurrences: List[tuple[datetime, datetime]] = []

    if freq == "NONE":
        if base_start.date() <= win_end and base_end.date() >= win_start:
            occurrences.append((base_start, base_end))
    else:
        max_cap = min(count_limit or 200, 200)
        generated = 0
        hard_end = min(win_end, until_date) if until_date else win_end

        if freq == "DAILY":
            cur = base_start
            while cur.date() <= hard_end and generated < max_cap:
                cur_end = cur + duration
                generated += 1
                if cur_end.date() >= win_start:
                    occurrences.append((cur, cur_end))
                cur = cur + timedelta(days=interval)

        elif freq == "WEEKLY":
            target_weekdays = sorted({DAY_CODE_TO_WEEKDAY[c] for c in by_day}) or [base_start.weekday()]
            week_start = base_start.date() - timedelta(days=base_start.weekday())
            while week_start <= hard_end and generated < max_cap:
                for wd in target_weekdays:
                    cand_date = week_start + timedelta(days=wd)
                    if cand_date < base_start.date():
                        continue
                    if cand_date > hard_end or generated >= max_cap:
                        break
                    cur = datetime.combine(cand_date, base_start.time())
                    cur_end = cur + duration
                    generated += 1
                    if cur_end.date() >= win_start:
                        occurrences.append((cur, cur_end))
                week_start += timedelta(weeks=interval)

        elif freq == "MONTHLY":
            step = 0
            day_target = int(by_month_day) if by_month_day else base_start.day
            while generated < max_cap:
                cur = _add_months(base_start, step * interval, target_day=day_target)
                if cur.date() > hard_end:
                    break
                cur_end = cur + duration
                generated += 1
                if cur_end.date() >= win_start:
                    occurrences.append((cur, cur_end))
                step += 1

        elif freq == "YEARLY":
            step = 0
            while generated < max_cap:
                cur = _add_months(base_start, step * 12 * interval, target_day=base_start.day)
                if cur.date() > hard_end:
                    break
                cur_end = cur + duration
                generated += 1
                if cur_end.date() >= win_start:
                    occurrences.append((cur, cur_end))
                step += 1

    owner_name = (getattr(s.user, "real_name", None) or getattr(s.user, "username", None)) if s.user else None
    results: List[Dict[str, Any]] = []
    for idx, (occ_start, occ_end) in enumerate(occurrences):
        start_d_str = occ_start.date().isoformat()
        end_d_str = occ_end.date().isoformat()
        results.append({
            "id": s.id if idx == 0 and freq == "NONE" else f"{s.id}_{idx}_{start_d_str}",
            "schedule_id": s.id,
            "source": "SCHEDULE",
            "user_id": s.user_id,
            "owner_name": owner_name,
            "title": s.title,
            "content": s.content,
            "category": s.category,
            "scope": s.scope,
            "color": s.color,
            "start_at": occ_start.strftime("%Y-%m-%dT%H:%M"),
            "end_at": occ_end.strftime("%Y-%m-%dT%H:%M"),
            "date": start_d_str,
            "endDate": end_d_str if end_d_str != start_d_str else None,
            "time": "종일" if s.is_all_day else occ_start.strftime("%H:%M"),
            "is_all_day": s.is_all_day,
            "display_mode": s.display_mode,
            "importance": s.importance,
            "is_dday": s.is_dday,
            "is_holiday": s.category == "HOLIDAY",
            "recurrence": rule or {"freq": "NONE", "interval": 1, "byDay": [], "byMonthDay": None, "until": None, "count": None},
        })
    return results


def _collect_dayoff_events(
    db: Session,
    current_user: User,
    win_start: date,
    win_end: date,
    include_all_office: bool,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    - 내 결근계(개인 스케줄) 조회
    - Tier 2(rank >= 2)인 경우 사무실 직원 전체 결근계 조회 (fcfs 운전직 제외)
    """
    policy = get_dayoff_policy(db)
    q = (
        db.query(DayOff)
        .options(joinedload(DayOff.user).joinedload(User.profile))
        .filter(
            and_(
                DayOff.is_deleted == False,
                DayOff.date >= win_start,
                DayOff.date <= win_end,
                DayOff.status.in_([DayOffStatus.REQUESTED.value, DayOffStatus.APPROVED.value]),
            )
        )
        .order_by(DayOff.date.asc(), DayOff.user_id.asc())
    )

    if not include_all_office:
        q = q.filter(DayOff.user_id == current_user.id)

    rows = q.all()

    # 연속 휴무 그룹화 (user_id + group_id + type + status)
    buckets: Dict[str, List[DayOff]] = {}
    for r in rows:
        is_mine = r.user_id == current_user.id
        is_office_staff = bool(r.user and not is_fcfs_user(r.user, policy))
        if not is_mine and not (include_all_office and is_office_staff):
            continue
        key = f"{r.user_id}|{r.group_id or f's-{r.id}'}|{r.type}|{r.status}"
        buckets.setdefault(key, []).append(r)

    calendar_items: List[Dict[str, Any]] = []
    my_dayoffs: List[Dict[str, Any]] = []
    office_dayoffs: List[Dict[str, Any]] = []

    for key, group_rows in buckets.items():
        group_rows.sort(key=lambda x: x.date)
        # 연속 일자 분리
        runs: List[List[DayOff]] = []
        cur_run = [group_rows[0]]
        for item in group_rows[1:]:
            if item.date == cur_run[-1].date:
                continue
            if item.date == cur_run[-1].date + timedelta(days=1):
                cur_run.append(item)
            else:
                runs.append(cur_run)
                cur_run = [item]
        runs.append(cur_run)

        for run in runs:
            first = run[0]
            last = run[-1]
            u = first.user
            staff_name = (u.real_name or u.username) if u else f"사원#{first.user_id}"
            type_label = DAYOFF_TYPE_LABELS.get(first.type, first.type)
            status_label = "승인" if first.status == "APPROVED" else "대기"
            is_mine = first.user_id == current_user.id
            is_office_staff = bool(u and not is_fcfs_user(u, policy))

            title = f"{staff_name} · {type_label}({status_label})"
            item_dict = {
                "id": f"dayoff_{first.id}",
                "dayoff_id": first.id,
                "source": "DAYOFF",
                "user_id": first.user_id,
                "staff_name": staff_name,
                "primary_group": u.primary_group if u else None,
                "is_mine": is_mine,
                "is_office_staff": is_office_staff,
                "title": title,
                "content": first.memo,
                "category": "DAYOFF",
                "scope": "PERSONAL" if is_mine else "OFFICE",
                "dayoff_type": first.type,
                "dayoff_status": first.status,
                "date": first.date.isoformat(),
                "endDate": last.date.isoformat() if last.date != first.date else None,
                "days_count": len(run),
                "time": "종일",
                "is_all_day": True,
                "display_mode": "bar",
                "importance": 2,
                "is_dday": False,
                "is_holiday": False,
            }
            calendar_items.append(item_dict)
            if is_mine:
                my_dayoffs.append(item_dict)
            if include_all_office and is_office_staff:
                office_dayoffs.append(item_dict)

    return calendar_items, my_dayoffs, office_dayoffs


def get_schedules_for_user(
    db: Session,
    current_user: User,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    rank = get_user_rank_val(current_user)
    is_tier2 = rank >= 2

    # 1. Schedule 테이블 조회: 본인 개인일정 + 전사/공휴일(GLOBAL) + 사무실 일정(OFFICE)은 모든 사원에게 공개
    allowed_scopes = ["GLOBAL", "OFFICE"]

    q = (
        db.query(Schedule)
        .options(joinedload(Schedule.user))
        .filter(
            and_(
                Schedule.is_deleted == False,
                or_(
                    Schedule.user_id == current_user.id,
                    Schedule.scope.in_(allowed_scopes),
                ),
            )
        )
        .order_by(Schedule.start_at.asc(), Schedule.id.asc())
    )
    rows = q.all()

    schedule_events: List[Dict[str, Any]] = []
    for row in rows:
        schedule_events.extend(_expand_schedule_occurrences(row, start_date, end_date))

    # 2. 결근계(DayOff) 오버레이: 본인 결근계 + Tier 2는 사무실 직원 전체 결근계
    dayoff_events, my_dayoffs, office_dayoffs = _collect_dayoff_events(
        db=db,
        current_user=current_user,
        win_start=start_date,
        win_end=end_date,
        include_all_office=is_tier2,
    )

    all_events = sorted(
        schedule_events + dayoff_events,
        key=lambda x: (x["date"], 0 if x["category"] == "HOLIDAY" else 1, str(x["title"])),
    )

    return {
        "events": all_events,
        "schedules": schedule_events,
        "my_dayoffs": my_dayoffs,
        "office_dayoffs": office_dayoffs,
        "user_rank": rank,
        "is_tier2": is_tier2,
        "can_manage_office": is_tier2,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def create_schedule(db: Session, current_user: User, payload: Any) -> Schedule:
    rank = get_user_rank_val(current_user)
    cat = payload.category
    if cat in {"HOLIDAY", "OFFICE", "GLOBAL"} and rank < 2:
        raise HTTPException(
            status_code=403,
            detail="공휴일·사무실·전사 일정 등록은 Tier 2(Rank 2 이상) 권한이 필요합니다.",
        )

    end_at = payload.end_at if (payload.end_at and payload.end_at >= payload.start_at) else payload.start_at
    rule_dict = payload.recurrence.model_dump() if payload.recurrence else {
        "freq": "NONE",
        "interval": 1,
        "byDay": [],
        "byMonthDay": None,
        "until": None,
        "count": None,
    }

    obj = Schedule(
        user_id=current_user.id,
        title=payload.title.strip(),
        content=payload.content,
        category=cat,
        scope=derive_scope(cat),
        color=payload.color or ("#ef4444" if cat == "HOLIDAY" else "#3b82f6"),
        start_at=payload.start_at,
        end_at=end_at,
        is_all_day=True if cat == "HOLIDAY" else payload.is_all_day,
        display_mode=payload.display_mode if rank >= 2 else "bar",
        importance=payload.importance,
        is_dday=payload.is_dday,
        recurrence_rule=rule_dict,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_schedule(db: Session, current_user: User, schedule_id: int, payload: Any) -> Schedule:
    obj = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.is_deleted == False).first()
    if not obj:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")

    rank = get_user_rank_val(current_user)
    if obj.user_id != current_user.id:
        if not (rank >= 2 and obj.scope in {"OFFICE", "GLOBAL"}):
            raise HTTPException(status_code=403, detail="해당 일정을 수정할 권한이 없습니다.")

    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"]:
        if data["category"] in {"HOLIDAY", "OFFICE", "GLOBAL"} and rank < 2:
            raise HTTPException(status_code=403, detail="공휴일·사무실·전사 일정 변경은 Tier 2 이상만 가능합니다.")
        obj.scope = derive_scope(data["category"])

    if "recurrence" in data:
        rec = data.pop("recurrence")
        obj.recurrence_rule = rec if isinstance(rec, dict) else (rec.model_dump() if rec else {})

    for k, v in data.items():
        setattr(obj, k, v)

    if obj.end_at and obj.end_at < obj.start_at:
        obj.end_at = obj.start_at
    obj.updated_at = datetime.now()
    db.commit()
    db.refresh(obj)
    return obj


def delete_schedule(db: Session, current_user: User, schedule_id: int) -> None:
    obj = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.is_deleted == False).first()
    if not obj:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")

    rank = get_user_rank_val(current_user)
    if obj.user_id != current_user.id:
        if not (rank >= 2 and obj.scope in {"OFFICE", "GLOBAL"}):
            raise HTTPException(status_code=403, detail="해당 일정을 삭제할 권한이 없습니다.")

    obj.is_deleted = True
    obj.updated_at = datetime.now()
    db.commit()
