import calendar
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import and_, func

from core.effective import pick
from models import DayOff, DayOffPolicy, User, SystemConfig
from domain.dayoff.dayoff_schema import DayOffCreate, DayOffStatus

DAYOFF_POLICY_KEY = "dayoff_policy"
DAYOFF_DATE_OVERRIDES_KEY = "dayoff_date_overrides"
INITIAL_EFFECTIVE_DATE = date(2020, 1, 1)

DEFAULT_DAYOFF_POLICY: Dict[str, Any] = {
    "classify_mode": "BOTH",
    "fcfs_groups": ["운전직", "운수팀", "운수1팀", "운수2팀"],
    "fcfs_ranks": [1],
    "daily_quota": 3,
    "date_overrides": {},
    "max_monthly_count": 0,      # 월별 최대 결근 신청 횟수 (0=제한 없음)
    "max_days_per_request": 0,   # 1회 신청 시 최대 사용 일수 (0=제한 없음)
    "min_advance_days": 0,       # 최소 신청 가능일 (D+X일부터, 0=오늘 D+0부터)
    "max_advance_days": 0,       # 최대 신청 가능일 (D+Y일까지, 0=제한 없음)
    "etc": {},                   # 확장용 JSONB
}


def _parse_date(val: Any) -> Optional[date]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val.strip()[:10])
        except ValueError:
            return None
    return None


def _non_neg_int(val: Any, fallback: int) -> int:
    try:
        return max(0, int(val))
    except (ValueError, TypeError):
        return fallback


def normalize_policy(raw: Optional[dict], base: Optional[dict] = None) -> Dict[str, Any]:
    """base(직전 정책) 위에서 None이 아닌 값만 덮어쓰며 정제합니다."""
    seed = dict(DEFAULT_DAYOFF_POLICY)
    if isinstance(base, dict):
        for k in DEFAULT_DAYOFF_POLICY:
            if k in base and base[k] is not None:
                seed[k] = list(base[k]) if isinstance(base[k], list) else (dict(base[k]) if isinstance(base[k], dict) else base[k])

    data = dict(seed)
    if isinstance(raw, dict):
        if raw.get("classify_mode") is not None:
            mode = str(raw["classify_mode"]).upper()
            if mode in ("GROUP", "RANK", "BOTH"):
                data["classify_mode"] = mode

        if raw.get("fcfs_groups") is not None and isinstance(raw.get("fcfs_groups"), list):
            data["fcfs_groups"] = [str(g).strip() for g in raw["fcfs_groups"] if str(g).strip()]

        if raw.get("fcfs_ranks") is not None and isinstance(raw.get("fcfs_ranks"), list):
            ranks = []
            for r in raw["fcfs_ranks"]:
                try:
                    rv = int(r)
                    if 0 <= rv <= 9:
                        ranks.append(rv)
                except (ValueError, TypeError):
                    pass
            data["fcfs_ranks"] = sorted(list(set(ranks)))

        if raw.get("daily_quota") is not None:
            data["daily_quota"] = _non_neg_int(raw["daily_quota"], seed["daily_quota"])

        if raw.get("date_overrides") is not None and isinstance(raw.get("date_overrides"), dict):
            overrides = {}
            for k, v in raw["date_overrides"].items():
                k_str = str(k).strip()
                if len(k_str) == 10 and v is not None:
                    overrides[k_str] = _non_neg_int(v, 0)
            data["date_overrides"] = overrides

        if raw.get("max_monthly_count") is not None:
            data["max_monthly_count"] = _non_neg_int(raw["max_monthly_count"], seed["max_monthly_count"])

        if raw.get("max_days_per_request") is not None:
            data["max_days_per_request"] = _non_neg_int(raw["max_days_per_request"], seed["max_days_per_request"])

        if raw.get("min_advance_days") is not None:
            data["min_advance_days"] = _non_neg_int(raw["min_advance_days"], seed["min_advance_days"])

        if raw.get("max_advance_days") is not None:
            data["max_advance_days"] = _non_neg_int(raw["max_advance_days"], seed["max_advance_days"])

        if raw.get("etc") is not None and isinstance(raw.get("etc"), dict):
            data["etc"] = dict(raw["etc"])

    return data


def _validate_advance_window(policy_data: Dict[str, Any]) -> None:
    """최대 신청 가능일(D+Y)이 설정된 경우 최소 신청 가능일(D+X)보다 작지 않도록 검증합니다."""
    min_d = int(policy_data.get("min_advance_days") or 0)
    max_d = int(policy_data.get("max_advance_days") or 0)
    if max_d > 0 and max_d < min_d:
        raise HTTPException(
            status_code=400,
            detail=f"최대 신청 가능일(D+{max_d})은 최소 신청 가능일(D+{min_d})보다 작을 수 없습니다."
        )


def _policy_column_values(merged: Dict[str, Any]) -> Dict[str, Any]:
    """정제된 정책 딕셔너리에서 DayOffPolicy 테이블 데이터 컬럼 매핑을 생성합니다."""
    return {
        "classify_mode": merged["classify_mode"],
        "fcfs_groups": merged["fcfs_groups"],
        "fcfs_ranks": merged["fcfs_ranks"],
        "daily_quota": merged["daily_quota"],
        "date_overrides": merged["date_overrides"],
        "max_monthly_count": merged["max_monthly_count"],
        "max_days_per_request": merged["max_days_per_request"],
        "min_advance_days": merged["min_advance_days"],
        "max_advance_days": merged["max_advance_days"],
        "etc": merged["etc"],
    }


def compute_request_window(policy: Dict[str, Any], base_date: Optional[date] = None) -> Dict[str, Any]:
    """신청 기준일(D) 대비 신청 가능한 최소·최대 날짜 범위를 계산합니다."""
    anchor = base_date or date.today()
    min_adv = max(0, int(policy.get("min_advance_days") or 0))
    max_adv = max(0, int(policy.get("max_advance_days") or 0))
    return {
        "today": str(anchor),
        "min_advance_days": min_adv,
        "max_advance_days": max_adv,
        "min_date": str(anchor + timedelta(days=min_adv)),
        "max_date": str(anchor + timedelta(days=max_adv)) if max_adv > 0 else None,
    }


def policy_row_to_dict(row: DayOffPolicy) -> Dict[str, Any]:
    return {
        "id": row.id,
        "effective_date": str(row.effective_date),
        "classify_mode": row.classify_mode or "BOTH",
        "fcfs_groups": list(row.fcfs_groups or []),
        "fcfs_ranks": list(row.fcfs_ranks or []),
        "daily_quota": int(row.daily_quota if row.daily_quota is not None else 3),
        "date_overrides": dict(row.date_overrides or {}),
        "max_monthly_count": int(row.max_monthly_count or 0),
        "max_days_per_request": int(row.max_days_per_request or 0),
        "min_advance_days": int(row.min_advance_days or 0),
        "max_advance_days": int(row.max_advance_days or 0),
        "etc": dict(row.etc or {}),
        "is_deleted": bool(row.is_deleted),
        "create_date": row.create_date.isoformat() if row.create_date else None,
    }


def ensure_initial_dayoff_policy(db: Session) -> None:
    """dayoff_policy 테이블이 비어있다면 기존 SystemConfig 또는 기본값으로 최초 1건을 시드합니다."""
    has_active = db.query(DayOffPolicy.id).filter(DayOffPolicy.is_deleted == False).first()
    if has_active:
        return

    legacy_cfg = db.query(SystemConfig).filter(SystemConfig.key == DAYOFF_POLICY_KEY).first()
    raw = legacy_cfg.value if (legacy_cfg and isinstance(legacy_cfg.value, dict)) else None
    normalized = normalize_policy(raw)

    seed_row = DayOffPolicy(
        effective_date=INITIAL_EFFECTIVE_DATE,
        **_policy_column_values(normalized),
        is_deleted=False,
        create_date=datetime.now(),
    )
    db.add(seed_row)
    db.commit()


def get_all_dayoff_policies(db: Session) -> List[DayOffPolicy]:
    """삭제되지 않은 모든 DayOffPolicy 행을 최신 적용일 순으로 반환합니다."""
    ensure_initial_dayoff_policy(db)
    return (
        db.query(DayOffPolicy)
        .filter(DayOffPolicy.is_deleted == False)
        .order_by(DayOffPolicy.effective_date.desc(), DayOffPolicy.id.desc())
        .all()
    )


def resolve_policy_for_date(policy_rows: List[DayOffPolicy], target_date: date) -> Dict[str, Any]:
    """주어진 레코드 목록에서 target_date 기준 유효한 정책을 pick()으로 선택해 dict로 반환합니다."""
    picked = pick(policy_rows, target_date)
    if picked is not None:
        return policy_row_to_dict(picked)
    if policy_rows:
        return policy_row_to_dict(policy_rows[-1])
    return dict(DEFAULT_DAYOFF_POLICY)


def get_dayoff_policy(db: Session, as_of: Optional[date] = None) -> Dict[str, Any]:
    rows = get_all_dayoff_policies(db)
    return resolve_policy_for_date(rows, as_of or date.today())


def get_reserved_dayoff_policy(db: Session, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """오늘 이후 적용 예정인 미삭제 예약 정책(최대 1건 유지 원칙)을 반환합니다."""
    anchor = today or date.today()
    row = (
        db.query(DayOffPolicy)
        .filter(
            DayOffPolicy.is_deleted == False,
            DayOffPolicy.effective_date > anchor,
        )
        .order_by(DayOffPolicy.effective_date.desc(), DayOffPolicy.id.desc())
        .first()
    )
    return policy_row_to_dict(row) if row else None


def get_date_overrides(db: Session) -> Dict[str, int]:
    """
    특정일 예외 정원 맵('YYYY-MM-DD' -> 정원)을 반환합니다.
    정책 이력(DayOffPolicy)과 완전히 분리하여 SystemConfig 단일 키로 관리합니다.
    """
    cfg = db.query(SystemConfig).filter(SystemConfig.key == DAYOFF_DATE_OVERRIDES_KEY).first()
    if cfg and isinstance(cfg.value, dict):
        return {str(k): max(0, int(v)) for k, v in cfg.value.items() if v is not None}

    # 최초 1회: 기존 DayOffPolicy.date_overrides에 있던 값을 안전하게 이관
    migrated: Dict[str, int] = {}
    legacy_rows = (
        db.query(DayOffPolicy)
        .filter(DayOffPolicy.is_deleted == False)
        .order_by(DayOffPolicy.effective_date.asc(), DayOffPolicy.id.asc())
        .all()
    )
    for r in legacy_rows:
        if isinstance(r.date_overrides, dict):
            for k, v in r.date_overrides.items():
                k_str = str(k).strip()
                if len(k_str) == 10 and v is not None:
                    migrated[k_str] = max(0, int(v))

    cfg = SystemConfig(
        key=DAYOFF_DATE_OVERRIDES_KEY,
        value=migrated,
        description="결근계 특정일 예외 정원 맵 (YYYY-MM-DD -> quota)",
    )
    db.add(cfg)
    db.commit()
    return migrated


def save_dayoff_policy(db: Session, policy_in: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append-Only 정책 등록:
    - 적용일이 미래(> today)이면 기존 예약 정책을 소프트 삭제하고 새 예약 1건만 INSERT합니다.
    - 적용일이 오늘(<= today)이면 예약이 없는 상태에서만 오늘 날짜로 새 레코드를 INSERT합니다.
    """
    today = date.today()
    ensure_initial_dayoff_policy(db)

    eff_date = _parse_date(policy_in.get("effective_date")) or today
    existing_reserved = (
        db.query(DayOffPolicy)
        .filter(
            DayOffPolicy.is_deleted == False,
            DayOffPolicy.effective_date > today,
        )
        .all()
    )

    if eff_date > today:
        for r in existing_reserved:
            r.is_deleted = True
    else:
        if existing_reserved:
            raise HTTPException(
                status_code=409,
                detail="예약된 정책이 있어 현재 설정을 변경할 수 없습니다. 예약을 취소하거나 예약 내용을 수정해 주세요.",
            )
        eff_date = today

    rows = (
        db.query(DayOffPolicy)
        .filter(DayOffPolicy.is_deleted == False)
        .order_by(DayOffPolicy.effective_date.desc(), DayOffPolicy.id.desc())
        .all()
    )
    base_dict = resolve_policy_for_date(rows, eff_date)
    merged = normalize_policy(policy_in, base=base_dict)
    merged["date_overrides"] = {}  # 예외 정원은 SystemConfig로 분리
    _validate_advance_window(merged)

    new_row = DayOffPolicy(
        effective_date=eff_date,
        **_policy_column_values(merged),
        is_deleted=False,
        create_date=datetime.now(),
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return policy_row_to_dict(new_row)


def delete_dayoff_policy_row(db: Session, policy_id: int) -> bool:
    """특정 id의 정책 레코드를 논리 삭제(is_deleted=True)합니다. 최소 1건은 유지합니다."""
    active_rows = get_all_dayoff_policies(db)
    target = next((r for r in active_rows if r.id == policy_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="삭제할 정책 레코드를 찾을 수 없습니다.")
    if len(active_rows) <= 1:
        raise HTTPException(status_code=400, detail="최소 1개의 기본 정책 레코드는 유지해야 합니다.")

    target.is_deleted = True
    db.commit()
    return True


def update_date_overrides(db: Session, dates: List[str], quota: Optional[int]) -> Dict[str, int]:
    """
    특정일 예외 정원만 독립적으로 갱신합니다. (DayOffPolicy 이력과 완전 분리)
    """
    overrides = dict(get_date_overrides(db))

    for d_str in dates:
        clean_d = str(d_str).strip()
        parsed_d = _parse_date(clean_d)
        if not parsed_d or len(clean_d) != 10:
            continue
        if quota is None or quota < 0:
            overrides.pop(clean_d, None)
        else:
            overrides[clean_d] = int(quota)

    cfg = db.query(SystemConfig).filter(SystemConfig.key == DAYOFF_DATE_OVERRIDES_KEY).first()
    if cfg:
        cfg.value = overrides
        flag_modified(cfg, "value")
    else:
        cfg = SystemConfig(
            key=DAYOFF_DATE_OVERRIDES_KEY,
            value=overrides,
            description="결근계 특정일 예외 정원 맵 (YYYY-MM-DD -> quota)",
        )
        db.add(cfg)

    db.commit()
    return overrides


def get_user_rank_val(user: Optional[User]) -> int:
    if not user:
        return 0
    if callable(getattr(user, "rank", None)):
        return int(user.rank() or 0)
    if getattr(user, "profile", None) and user.profile.rank_level is not None:
        return int(user.profile.rank_level)
    return 0


def is_fcfs_user(user: Optional[User], policy: Dict[str, Any]) -> bool:
    """
    사용자가 운전직(선착순제: FCFS) 대상인지 판별합니다.
    - False 반환 시 사무직(신청·승인제: APPROVAL)으로 동작합니다.
    """
    if not user:
        return False

    mode = policy.get("classify_mode", "BOTH")
    fcfs_groups = set(policy.get("fcfs_groups") or [])
    fcfs_ranks = set(policy.get("fcfs_ranks") or [])

    raw_groups = user.all_groups() if callable(getattr(user, "all_groups", None)) else (getattr(user, "all_groups", None) or [])
    user_groups = set(raw_groups)
    if user.primary_group:
        user_groups.add(user.primary_group)

    user_rank = get_user_rank_val(user)

    group_match = bool(fcfs_groups and (user_groups & fcfs_groups))
    rank_match = user_rank in fcfs_ranks

    if mode == "GROUP":
        return group_match
    if mode == "RANK":
        return rank_match
    return group_match or rank_match


def get_quota_for_date(
    date_str: str,
    policy: Dict[str, Any],
    date_overrides: Optional[Dict[str, int]] = None,
) -> int:
    overrides = date_overrides if date_overrides is not None else (policy.get("date_overrides") or {})
    if date_str in overrides:
        return max(0, int(overrides[date_str]))
    return max(0, int(policy.get("daily_quota", 3)))


def get_user_monthly_request_count(db: Session, user_id: int, year: int, month: int) -> int:
    """특정 월에 사용자가 제출한 활성 결근계(group_id 또는 단건) 횟수를 반환합니다."""
    _, last_day = calendar.monthrange(year, month)
    start_d = date(year, month, 1)
    end_d = date(year, month, last_day)

    rows = (
        db.query(DayOff.id, DayOff.group_id)
        .filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.date >= start_d,
                DayOff.date <= end_d,
                DayOff.is_deleted == False,
                DayOff.status.in_([DayOffStatus.REQUESTED.value, DayOffStatus.APPROVED.value]),
            )
        )
        .all()
    )
    batches = {r.group_id or f"single-{r.id}" for r in rows}
    return len(batches)


def get_fcfs_approved_count_for_date(db: Session, target_date: date, policy: Dict[str, Any]) -> int:
    """특정 날짜에 선착순(운전직) 대상자 중 승인(APPROVED)된 휴무 인원 수를 반환합니다."""
    rows = (
        db.query(DayOff)
        .options(joinedload(DayOff.user).joinedload(User.profile))
        .filter(
            and_(
                DayOff.date == target_date,
                DayOff.is_deleted == False,
                DayOff.status == DayOffStatus.APPROVED.value,
            )
        )
        .all()
    )
    count = 0
    for r in rows:
        if r.user and is_fcfs_user(r.user, policy):
            count += 1
    return count


def get_monthly_quota_status(
    db: Session,
    year: int,
    month: int,
    current_user: Optional[User] = None
) -> Dict[str, Any]:
    """
    지정된 연/월의 일자별 선착순 정원(Quota), 현재 확정 인원, 마감 여부를 반환합니다.
    각 날짜별로 pick()으로 선택된 정책 레코드를 적용해 과거/현재/미래 정원이 공존합니다.
    """
    policy_rows = get_all_dayoff_policies(db)
    date_overrides = get_date_overrides(db)
    _, last_day = calendar.monthrange(year, month)
    start_d = date(year, month, 1)
    end_d = date(year, month, last_day)

    rows = (
        db.query(DayOff)
        .options(joinedload(DayOff.user).joinedload(User.profile))
        .filter(
            and_(
                DayOff.date >= start_d,
                DayOff.date <= end_d,
                DayOff.is_deleted == False,
                DayOff.status == DayOffStatus.APPROVED.value,
            )
        )
        .all()
    )

    day_policies: Dict[str, Dict[str, Any]] = {}
    for day_num in range(1, last_day + 1):
        d_obj = date(year, month, day_num)
        day_policies[str(d_obj)] = resolve_policy_for_date(policy_rows, d_obj)

    counts_by_date: Dict[str, int] = {}
    names_by_date: Dict[str, List[str]] = {}
    for r in rows:
        d_str = str(r.date)
        d_policy = day_policies.get(d_str) or resolve_policy_for_date(policy_rows, r.date)
        if r.user and is_fcfs_user(r.user, d_policy):
            counts_by_date[d_str] = counts_by_date.get(d_str, 0) + 1
            staff_name = r.user.real_name or r.user.username
            names_by_date.setdefault(d_str, []).append(staff_name)

    days_map: Dict[str, Any] = {}
    for day_num in range(1, last_day + 1):
        d_str = f"{year:04d}-{month:02d}-{day_num:02d}"
        d_policy = day_policies[d_str]
        quota = get_quota_for_date(d_str, d_policy, date_overrides)
        approved_cnt = counts_by_date.get(d_str, 0)
        remaining = max(0, quota - approved_cnt)
        days_map[d_str] = {
            "date": d_str,
            "quota": quota,
            "policy_id": d_policy.get("id"),
            "effective_date": d_policy.get("effective_date"),
            "is_override": d_str in date_overrides,
            "approved_count": approved_cnt,
            "remaining": remaining,
            "is_full": approved_cnt >= quota,
            "approved_names": names_by_date.get(d_str, [])
        }

    today = date.today()
    ref_date = today if (year == today.year and month == today.month) else start_d
    summary_policy = resolve_policy_for_date(policy_rows, ref_date)
    today_policy = resolve_policy_for_date(policy_rows, today)
    request_window = compute_request_window(today_policy, today)
    user_is_fcfs = is_fcfs_user(current_user, summary_policy) if current_user else False

    monthly_used = (
        get_user_monthly_request_count(db, current_user.id, year, month)
        if current_user else 0
    )

    return {
        "policy": summary_policy,
        "today_policy": today_policy,
        "request_window": request_window,
        "user_mode": "FCFS" if user_is_fcfs else "APPROVAL",
        "user_primary_group": current_user.primary_group if current_user else None,
        "user_rank_level": get_user_rank_val(current_user),
        "monthly_used_count": monthly_used,
        "year": year,
        "month": month,
        "days": days_map
    }


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

    # 0. 결근계 사용 가능 날짜 범위(D+X ~ D+Y) 및 1회 신청 최대 일수 검사
    today = date.today()
    today_policy = resolve_policy_for_date(policy_rows, today)
    req_window = compute_request_window(today_policy, today)
    min_adv = req_window["min_advance_days"]
    max_adv = req_window["max_advance_days"]

    for date_item in sorted_dates:
        days_ahead = (date_item - today).days
        if days_ahead < min_adv:
            raise HTTPException(
                status_code=400,
                detail=f"{date_item}은(는) 신청 가능 최소일(오늘 기준 D+{min_adv}일, {req_window['min_date']}부터) 이전이라 신청할 수 없습니다."
            )
        if max_adv > 0 and days_ahead > max_adv:
            raise HTTPException(
                status_code=400,
                detail=f"{date_item}은(는) 신청 가능 최대일(오늘 기준 D+{max_adv}일, {req_window['max_date']}까지)을 초과하여 신청할 수 없습니다."
            )

    req_policy = resolve_policy_for_date(policy_rows, sorted_dates[0])
    max_days = int(req_policy.get("max_days_per_request") or 0)
    if max_days > 0 and len(sorted_dates) > max_days:
        raise HTTPException(
            status_code=400,
            detail=f"1회 결근계 최대 신청 일수({max_days}일)를 초과할 수 없습니다. (선택: {len(sorted_dates)}일)"
        )

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

    # 1-2. 1회 신청 일수 재확인 & 월별 최대 사용 횟수 검사
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
