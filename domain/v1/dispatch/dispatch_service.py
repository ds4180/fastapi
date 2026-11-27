"""
============================================================================
[차량 배차 비즈니스 로직 & 설정·자동고지 서비스 (domain/v1/dispatch/dispatch_service.py)]
============================================================================
"""

from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _now_kst() -> datetime:
    """한국 표준시(Asia/Seoul) 기준 현재 시각을 반환합니다."""
    try:
        return datetime.now(KST)
    except Exception:
        return datetime.now(timezone(timedelta(hours=9)))

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from models import DayOff, Dispatch, RouteMaster, RouteTimetable, SystemConfig, User

try:
    from redis_config import rd as redis_client
except Exception:
    redis_client = None

DISPATCH_STATS_CACHE_PREFIX = "dispatch:driver_stats:"
DISPATCH_STATS_CACHE_TTL = 300
DISPATCH_TIMETABLE_ROTATION_CACHE_KEY = "dispatch:timetable_rotation_map"
DISPATCH_TIMETABLE_ROTATION_TTL = 1800

DISPATCH_SETTINGS_KEY = "dispatch_settings"
DISPATCH_AUTO_ANNOUNCE_STATE_KEY = "dispatch_auto_announce_state"
DISPATCH_PUBLISHED_DATES_KEY = "dispatch_published_dates"

DEFAULT_ROUTE_FLEET_RULES: List[Dict[str, Any]] = [
    {"keywords": ["121", "122"], "fleet_key": "121/122"},
    {"keywords": ["291", "292", "293"], "fleet_key": "291/292/293"},
]

DEFAULT_DRIVER_ASSIGN_COLORS: Dict[str, Dict[str, Any]] = {
    "reserve": {"enabled": True, "bg_color": "#dbeafe", "text_color": "#1e40af"},
    "cross": {"enabled": True, "bg_color": "#fde68a", "text_color": "#78350f"},
}

DEFAULT_DISPATCH_SETTINGS: Dict[str, Any] = {
    # 1. 배차 예고(사전 공개) 설정
    "preview_enabled": True,
    "preview_force_open": False,
    "preview_start_offset": 3,
    "preview_days": 5,
    "preview_open_time": "17:00",
    "preview_pause_message": "배차 조정 중으로 예고 열람이 일시 중지되었습니다.",
    # 2. 명일 배차 자동 고지 & 푸시 알림 설정
    "auto_announce_enabled": False,
    "auto_announce_time": "17:00",
    "auto_announce_push": True,
    "auto_announce_skip_if_confirmed": True,
    "auto_announce_title_template": "[명일 배차 고지] {target_date}",
    "auto_announce_body_template": "{target_date} 배차가 확정 고지되었습니다. 배차표에서 차량과 로번을 확인해 주세요.",
    "reannounce_title_template": "[명일 배차 변경 재공지] {target_date}",
    "reannounce_body_template": "{target_date} 배차가 수정되어 재배포되었습니다. 변경된 차량과 로번을 반드시 다시 확인해 주세요.",
    "announce_sender_min_rank": 4,
    # 2-1. 배차 확인(D-day/D-1) 및 예고(D+2+) 공개 정책 설정
    "confirm_d_day_always_open": True,
    "confirm_d1_require_announced": True,
    "preview_allow_draft": True,
    # 3. 노선-차량 매핑 & 표시·색상 설정
    "route_fleet_rules": DEFAULT_ROUTE_FLEET_RULES,
    "show_substitute_columns": True,
    "driver_assign_colors": DEFAULT_DRIVER_ASSIGN_COLORS,
    # 4. 투입 기사 공정배분 & 정합성 검증 설정
    "max_weekly_work_days": 4,
    "weekly_basis": "calendar_week",
    "min_rest_hours": 8,
    "night_metric_mode": "turn_count",
    "night_route_turn_rules": [],
    "night_morning_end": "06:00",
    "night_evening_start": "21:00",
    "stats_include_draft": True,
    "enable_validation_blink": True,
    "warn_prev_day_work": True,
}


def invalidate_driver_work_stats_cache() -> None:
    """기사별 운행 통계 Redis 캐시를 무효화합니다."""
    if redis_client is None:
        return
    try:
        keys = list(redis_client.scan_iter(match=f"{DISPATCH_STATS_CACHE_PREFIX}*"))
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass


def invalidate_timetable_rotation_cache() -> None:
    """노선 시간표 순환 맵 및 관련 통계 Redis 캐시를 무효화합니다."""
    if redis_client is not None:
        try:
            redis_client.delete(DISPATCH_TIMETABLE_ROTATION_CACHE_KEY)
        except Exception:
            pass
    invalidate_driver_work_stats_cache()


def _normalize_hhmm(val: Any, fallback: str = "17:00") -> str:
    s = str(val or "").strip()
    if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", s):
        return s
    return fallback


def _clamp_int(val: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        return max(min_val, min(max_val, int(val)))
    except (TypeError, ValueError):
        return fallback


def _normalize_hex_color(val: Any, fallback: str) -> str:
    s = str(val or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", s):
        return s.lower()
    return fallback


def _normalize_assign_colors(raw: Any) -> Dict[str, Dict[str, Any]]:
    src = raw if isinstance(raw, dict) else {}
    result: Dict[str, Dict[str, Any]] = {}
    for key, defaults in DEFAULT_DRIVER_ASSIGN_COLORS.items():
        item = src.get(key) if isinstance(src.get(key), dict) else {}
        result[key] = {
            "enabled": bool(item.get("enabled", defaults["enabled"])),
            "bg_color": _normalize_hex_color(item.get("bg_color"), defaults["bg_color"]),
            "text_color": _normalize_hex_color(item.get("text_color"), defaults["text_color"]),
        }
    return result


def _normalize_night_route_rules(raw: Any) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return clean
    for item in raw:
        if not isinstance(item, dict):
            continue
        kw = str(item.get("route_keyword") or "").strip()
        seqs = sorted(
            {int(x) for x in (item.get("turn_seqs") or []) if str(x).strip().isdigit() and int(x) > 0}
        )
        if kw and seqs:
            clean.append({"route_keyword": kw, "turn_seqs": seqs})
    return clean


def get_dispatch_settings(db: Session) -> Dict[str, Any]:
    """배차 앱 전역 설정을 SystemConfig에서 조회합니다."""
    row = db.query(SystemConfig).filter(SystemConfig.key == DISPATCH_SETTINGS_KEY).first()
    raw = row.value if row and isinstance(row.value, dict) else {}
    merged = {**DEFAULT_DISPATCH_SETTINGS, **raw}
    for legacy_key in ("night_turn_seqs", "night_include_last_turn", "disciplined_drivers"):
        merged.pop(legacy_key, None)
    merged["preview_enabled"] = bool(merged.get("preview_enabled", True))
    merged["preview_force_open"] = bool(merged.get("preview_force_open", False))
    merged["preview_start_offset"] = _clamp_int(merged.get("preview_start_offset"), 0, 30, 3)
    merged["preview_days"] = _clamp_int(merged.get("preview_days"), 1, 30, 5)
    merged["preview_open_time"] = _normalize_hhmm(merged.get("preview_open_time"), "17:00")
    merged["preview_pause_message"] = (
        str(merged.get("preview_pause_message") or "").strip()
        or DEFAULT_DISPATCH_SETTINGS["preview_pause_message"]
    )
    merged["auto_announce_enabled"] = bool(merged.get("auto_announce_enabled", False))
    merged["auto_announce_time"] = _normalize_hhmm(merged.get("auto_announce_time"), "17:00")
    merged["auto_announce_push"] = bool(merged.get("auto_announce_push", True))
    merged["auto_announce_skip_if_confirmed"] = bool(merged.get("auto_announce_skip_if_confirmed", True))
    merged["auto_announce_title_template"] = (
        str(merged.get("auto_announce_title_template") or "").strip()
        or DEFAULT_DISPATCH_SETTINGS["auto_announce_title_template"]
    )
    merged["auto_announce_body_template"] = (
        str(merged.get("auto_announce_body_template") or "").strip()
        or DEFAULT_DISPATCH_SETTINGS["auto_announce_body_template"]
    )
    merged["reannounce_title_template"] = (
        str(merged.get("reannounce_title_template") or "").strip()
        or DEFAULT_DISPATCH_SETTINGS["reannounce_title_template"]
    )
    merged["reannounce_body_template"] = (
        str(merged.get("reannounce_body_template") or "").strip()
        or DEFAULT_DISPATCH_SETTINGS["reannounce_body_template"]
    )
    merged["announce_sender_min_rank"] = _clamp_int(merged.get("announce_sender_min_rank"), 1, 10, 4)
    merged["confirm_d_day_always_open"] = bool(merged.get("confirm_d_day_always_open", True))
    merged["confirm_d1_require_announced"] = bool(merged.get("confirm_d1_require_announced", True))
    merged["preview_allow_draft"] = bool(merged.get("preview_allow_draft", True))
    merged["show_substitute_columns"] = bool(merged.get("show_substitute_columns", True))
    rules = merged.get("route_fleet_rules")
    if not isinstance(rules, list) or len(rules) == 0:
        merged["route_fleet_rules"] = DEFAULT_ROUTE_FLEET_RULES
    merged["driver_assign_colors"] = _normalize_assign_colors(merged.get("driver_assign_colors"))
    merged["max_weekly_work_days"] = _clamp_int(merged.get("max_weekly_work_days"), 1, 7, 4)
    merged["weekly_basis"] = (
        "rolling_7d" if merged.get("weekly_basis") == "rolling_7d" else "calendar_week"
    )
    merged["min_rest_hours"] = _clamp_int(merged.get("min_rest_hours"), 0, 24, 8)
    merged["night_metric_mode"] = (
        "time_range" if merged.get("night_metric_mode") == "time_range" else "turn_count"
    )
    merged["night_route_turn_rules"] = _normalize_night_route_rules(
        merged.get("night_route_turn_rules")
    )
    merged["night_morning_end"] = _normalize_hhmm(merged.get("night_morning_end"), "06:00")
    merged["night_evening_start"] = _normalize_hhmm(merged.get("night_evening_start"), "21:00")
    merged["stats_include_draft"] = bool(merged.get("stats_include_draft", True))
    merged["enable_validation_blink"] = bool(merged.get("enable_validation_blink", True))
    merged["warn_prev_day_work"] = bool(merged.get("warn_prev_day_work", True))
    return merged


def save_dispatch_settings(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """배차 앱 전역 설정을 SystemConfig에 저장합니다."""
    raw_rules = payload.get("route_fleet_rules")
    clean_rules: List[Dict[str, Any]] = []
    if isinstance(raw_rules, list):
        for item in raw_rules:
            if not isinstance(item, dict):
                continue
            fkey = str(item.get("fleet_key") or "").strip()
            kws = [str(k).strip() for k in (item.get("keywords") or []) if str(k).strip()]
            if fkey and kws:
                clean_rules.append({"keywords": kws, "fleet_key": fkey})
    if not clean_rules:
        clean_rules = DEFAULT_ROUTE_FLEET_RULES

    clean: Dict[str, Any] = {
        "preview_enabled": bool(payload.get("preview_enabled", True)),
        "preview_force_open": bool(payload.get("preview_force_open", False)),
        "preview_start_offset": _clamp_int(payload.get("preview_start_offset"), 0, 30, 3),
        "preview_days": _clamp_int(payload.get("preview_days"), 1, 30, 5),
        "preview_open_time": _normalize_hhmm(payload.get("preview_open_time"), "17:00"),
        "preview_pause_message": (
            str(payload.get("preview_pause_message") or "").strip()
            or DEFAULT_DISPATCH_SETTINGS["preview_pause_message"]
        ),
        "auto_announce_enabled": bool(payload.get("auto_announce_enabled", False)),
        "auto_announce_time": _normalize_hhmm(payload.get("auto_announce_time"), "17:00"),
        "auto_announce_push": bool(payload.get("auto_announce_push", True)),
        "auto_announce_skip_if_confirmed": bool(payload.get("auto_announce_skip_if_confirmed", True)),
        "auto_announce_title_template": (
            str(payload.get("auto_announce_title_template") or "").strip()
            or DEFAULT_DISPATCH_SETTINGS["auto_announce_title_template"]
        ),
        "auto_announce_body_template": (
            str(payload.get("auto_announce_body_template") or "").strip()
            or DEFAULT_DISPATCH_SETTINGS["auto_announce_body_template"]
        ),
        "reannounce_title_template": (
            str(payload.get("reannounce_title_template") or "").strip()
            or DEFAULT_DISPATCH_SETTINGS["reannounce_title_template"]
        ),
        "reannounce_body_template": (
            str(payload.get("reannounce_body_template") or "").strip()
            or DEFAULT_DISPATCH_SETTINGS["reannounce_body_template"]
        ),
        "announce_sender_min_rank": _clamp_int(payload.get("announce_sender_min_rank"), 1, 10, 4),
        "confirm_d_day_always_open": bool(payload.get("confirm_d_day_always_open", True)),
        "confirm_d1_require_announced": bool(payload.get("confirm_d1_require_announced", True)),
        "preview_allow_draft": bool(payload.get("preview_allow_draft", True)),
        "route_fleet_rules": clean_rules,
        "show_substitute_columns": bool(payload.get("show_substitute_columns", True)),
        "driver_assign_colors": _normalize_assign_colors(payload.get("driver_assign_colors")),
        "max_weekly_work_days": _clamp_int(payload.get("max_weekly_work_days"), 1, 7, 4),
        "weekly_basis": "rolling_7d" if payload.get("weekly_basis") == "rolling_7d" else "calendar_week",
        "min_rest_hours": _clamp_int(payload.get("min_rest_hours"), 0, 24, 8),
        "night_metric_mode": "time_range" if payload.get("night_metric_mode") == "time_range" else "turn_count",
        "night_route_turn_rules": _normalize_night_route_rules(payload.get("night_route_turn_rules")),
        "night_morning_end": _normalize_hhmm(payload.get("night_morning_end"), "06:00"),
        "night_evening_start": _normalize_hhmm(payload.get("night_evening_start"), "21:00"),
        "stats_include_draft": bool(payload.get("stats_include_draft", True)),
        "enable_validation_blink": bool(payload.get("enable_validation_blink", True)),
        "warn_prev_day_work": bool(payload.get("warn_prev_day_work", True)),
    }

    row = db.query(SystemConfig).filter(SystemConfig.key == DISPATCH_SETTINGS_KEY).first()
    if row:
        row.value = clean
    else:
        db.add(
            SystemConfig(
                key=DISPATCH_SETTINGS_KEY,
                value=clean,
                description="차량 배차 앱 전역 비즈니스 설정 (예고·자동고지·매핑)",
            )
        )
    db.commit()
    invalidate_driver_work_stats_cache()
    return clean


def compute_preview_window(settings: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """배차 예고 공개 범위(offsets 및 날짜 목록)를 계산합니다.

    정책(공개 시각 전 전체 잠금):
    - preview_enabled=False: 예고 일시 중지 (전체 잠금)
    - preview_force_open=False 이고 현재 시각(KST) < preview_open_time:
      해당일 공개 시각 이전이므로 예고 전체 잠금 (offsets=[], allowed_dates=[])
    - preview_force_open=True 또는 현재 시각(KST) >= preview_open_time:
      설정한 preview_start_offset ~ preview_start_offset + preview_days - 1 전체 공개
    """
    cur = now if now is not None else _now_kst()
    if cur.tzinfo is not None:
        cur = cur.astimezone(KST)
    today = cur.date()
    now_hhmm = cur.strftime("%H:%M")

    open_time = _normalize_hhmm(
        settings.get("preview_open_time"),
        DEFAULT_DISPATCH_SETTINGS["preview_open_time"],
    )

    if not settings.get("preview_enabled", True):
        return {
            "is_paused": True,
            "is_force_open": False,
            "open_time": open_time,
            "min_offset": None,
            "max_offset": None,
            "offsets": [],
            "allowed_dates": [],
            "reason": settings.get("preview_pause_message") or DEFAULT_DISPATCH_SETTINGS["preview_pause_message"],
        }

    start_offset = int(settings.get("preview_start_offset", DEFAULT_DISPATCH_SETTINGS["preview_start_offset"]))
    days = int(settings.get("preview_days", DEFAULT_DISPATCH_SETTINGS["preview_days"]))
    force_open = bool(settings.get("preview_force_open", False))

    if not force_open and now_hhmm < open_time:
        return {
            "is_paused": False,
            "is_force_open": False,
            "open_time": open_time,
            "min_offset": None,
            "max_offset": None,
            "offsets": [],
            "allowed_dates": [],
            "reason": f"배차 예고는 매일 {open_time} 이후부터 확인할 수 있습니다.",
        }

    max_offset = start_offset + days - 1
    if max_offset < start_offset:
        offsets: List[int] = []
    else:
        offsets = list(range(start_offset, max_offset + 1))

    allowed_dates = [(today + timedelta(days=off)).isoformat() for off in offsets]
    if not offsets:
        reason = f"배차 예고는 매일 {open_time} 이후부터 확인할 수 있습니다."
    else:
        reason = f"조회 가능 범위: 오늘 기준 +{offsets[0]}일 ~ +{offsets[-1]}일"

    return {
        "is_paused": False,
        "is_force_open": force_open,
        "open_time": open_time,
        "min_offset": offsets[0] if offsets else None,
        "max_offset": offsets[-1] if offsets else None,
        "offsets": offsets,
        "allowed_dates": allowed_dates,
        "reason": reason,
    }


def resolve_route_fleet(
    route_name: str,
    vehicles_by_group: Dict[str, List[str]],
    route_fleet_rules: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """노선명과 설정된 route_fleet_rules를 기반으로 전담 차량 풀을 동적 매칭합니다."""
    r_name = str(route_name or "")
    rules = route_fleet_rules if isinstance(route_fleet_rules, list) else DEFAULT_ROUTE_FLEET_RULES
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        keywords = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
        fleet_key = str(rule.get("fleet_key") or "").strip()
        if fleet_key and any(kw in r_name for kw in keywords):
            matched = vehicles_by_group.get(fleet_key)
            if isinstance(matched, list):
                return matched
    all_vehicles: List[str] = []
    seen = set()
    for arr in (vehicles_by_group or {}).values():
        if isinstance(arr, list):
            for v in arr:
                if v not in seen:
                    seen.add(v)
                    all_vehicles.append(v)
    return all_vehicles


def verify_custom_preview_access(db: Session, target_date: date) -> None:
    """일반 사원용 배차 조회 날짜 접근 가능 여부를 검증합니다."""
    now_kst = _now_kst()
    today = now_kst.date()
    tomorrow = today + timedelta(days=1)
    settings = get_dispatch_settings(db)
    if target_date in (today, tomorrow):
        return
    win = compute_preview_window(settings, now=now_kst)
    if win["is_paused"]:
        raise HTTPException(status_code=403, detail=win["reason"])
    if target_date.isoformat() not in win["allowed_dates"]:
        raise HTTPException(
            status_code=403,
            detail=f"{target_date.isoformat()} 배차 예고는 아직 공개 전입니다. ({win['reason']})",
        )


def get_published_dates_map(db: Session) -> Dict[str, Any]:
    """날짜별 배차 공개(배포) 상태 맵을 조회합니다. ({'YYYY-MM-DD': {'published_at': ..., 'mode': ...}})"""
    row = db.query(SystemConfig).filter(SystemConfig.key == DISPATCH_PUBLISHED_DATES_KEY).first()
    if row and isinstance(row.value, dict):
        return dict(row.value)
    return {}


def is_date_published(db: Session, target_date: date) -> bool:
    """해당 날짜의 배차가 공개(배포)되었는지 여부를 반환합니다. (날짜 단위 단일 진실 공급원)"""
    date_key = target_date.isoformat()
    pub_map = get_published_dates_map(db)
    if date_key in pub_map:
        entry = pub_map.get(date_key)
        if isinstance(entry, dict) and entry.get("published") is False:
            return False
        return True
    # 하위 호환: 기존에 행 단위 ANNOUNCED로 저장된 날짜도 공개된 것으로 인정
    return (
        db.query(Dispatch.id)
        .filter(Dispatch.target_date == target_date, Dispatch.status == "ANNOUNCED")
        .first()
        is not None
    )


def get_dispatch_date_state(db: Session, target_date: date) -> Dict[str, Any]:
    """
    [배차 상태 머신 단일 진실 공급원 (SSOT)]
    특정 날짜의 저장/확정/배포/재배포 가능 여부를 일관되게 계산합니다.
    - PAST (< today): 수정·저장·확정·배포 모두 불가
    - TODAY (== today): 긴급 수정 저장 가능
    - D_MINUS_1 (== today + 1): 저장·확정↔확정취소 무제한, 최초 배포 1회, 공개취소↔재배포 무제한
    - FUTURE (> today + 1): 언제든 DRAFT 저장 가능, 확정·배포 불가
    """
    from domain.v1.dispatch.dispatch_builder import query_active_routes_for_date

    today_kst = _now_kst().date()
    tomorrow_kst = today_kst + timedelta(days=1)
    if target_date < today_kst:
        date_role = "PAST"
    elif target_date == today_kst:
        date_role = "TODAY"
    elif target_date == tomorrow_kst:
        date_role = "D_MINUS_1"
    else:
        date_role = "FUTURE"

    date_key = target_date.isoformat()
    pub_map = get_published_dates_map(db)
    meta = pub_map.get(date_key) if isinstance(pub_map.get(date_key), dict) else None

    active_routes = query_active_routes_for_date(db, target_date)
    route_ids = [r["id"] for r in active_routes if isinstance(r, dict) and r.get("id")]

    total_count = 0
    saved_count = 0
    confirmed_count = 0
    announced_count = 0

    if route_ids:
        tt_ids = [
            tid
            for (tid,) in db.query(RouteTimetable.id)
            .filter(RouteTimetable.route_master_id.in_(route_ids))
            .all()
        ]
        total_count = len(tt_ids)
        if tt_ids:
            saved_count = (
                db.query(Dispatch.id)
                .filter(Dispatch.target_date == target_date, Dispatch.timetable_id.in_(tt_ids))
                .count()
            )
            confirmed_count = (
                db.query(Dispatch.id)
                .filter(
                    Dispatch.target_date == target_date,
                    Dispatch.timetable_id.in_(tt_ids),
                    Dispatch.status.in_(("CONFIRMED", "ANNOUNCED")),
                )
                .count()
            )
            announced_count = (
                db.query(Dispatch.id)
                .filter(
                    Dispatch.target_date == target_date,
                    Dispatch.timetable_id.in_(tt_ids),
                    Dispatch.status == "ANNOUNCED",
                )
                .count()
            )

    published = is_date_published(db, target_date)
    publish_count = int((meta or {}).get("publish_count") or (1 if (meta and meta.get("published", True)) else 0))
    was_published = bool(publish_count > 0 or (meta and meta.get("unpublished_at")))
    is_all_confirmed = bool(total_count > 0 and confirmed_count >= total_count)

    return {
        "target_date": date_key,
        "date_role": date_role,
        "published": published,
        "was_published": was_published,
        "publish_count": publish_count,
        "confirmed": is_all_confirmed,
        "confirmed_count": confirmed_count,
        "announced_count": announced_count,
        "saved_count": saved_count,
        "total_count": total_count,
        "meta": meta,
        "can_save_draft": date_role != "PAST",
        "can_confirm_toggle": date_role == "D_MINUS_1" and not published,
        "can_initial_publish": date_role == "D_MINUS_1" and is_all_confirmed and not published and not was_published,
        "can_republish": date_role == "D_MINUS_1" and is_all_confirmed and not published and was_published,
        "can_unpublish": date_role == "D_MINUS_1" and published,
    }


def set_date_published(
    db: Session,
    target_date: date,
    published: bool,
    *,
    mode: str = "manual",
) -> Dict[str, Any]:
    """
    전날(D-1) 배차의 공개(최초 배포 1회) / 공개 취소(무제한) / 재배포(무제한) 상태를 원자적으로 전이합니다.
    """
    date_key = target_date.isoformat()
    now_kst = _now_kst()
    tomorrow_kst = now_kst.date() + timedelta(days=1)

    if target_date != tomorrow_kst:
        raise HTTPException(
            status_code=400,
            detail="배차 배포 및 배포 취소는 운행 전날(D-1, 내일 배차)에만 수행할 수 있습니다.",
        )

    now_str = now_kst.strftime("%Y-%m-%d %H:%M")
    row = db.query(SystemConfig).filter(SystemConfig.key == DISPATCH_PUBLISHED_DATES_KEY).first()
    pub_map = dict(row.value) if (row and isinstance(row.value, dict)) else {}

    cutoff = (now_kst.date() - timedelta(days=30)).isoformat()
    pub_map = {k: v for k, v in pub_map.items() if str(k) >= cutoff}

    prev_meta = pub_map.get(date_key) if isinstance(pub_map.get(date_key), dict) else {}
    prev_published = bool(prev_meta.get("published", True)) if prev_meta else False
    prev_count = int(prev_meta.get("publish_count") or 0)
    if prev_count == 0 and prev_meta:
        prev_count = 1

    is_reannounce = False
    publish_count = prev_count

    if published:
        if prev_published:
            raise HTTPException(
                status_code=409,
                detail="이미 배포(공개) 중인 배차입니다. 재배포하려면 먼저 '배포 취소'를 실행해 주세요.",
            )
        is_reannounce = bool(prev_meta.get("unpublished_at")) or prev_count > 0
        publish_count = prev_count + 1
        pub_map[date_key] = {
            "published": True,
            "published_at": now_str,
            "mode": mode,
            "publish_count": publish_count,
            "is_reannounce": is_reannounce,
            "unpublished_at": prev_meta.get("unpublished_at"),
        }
    else:
        if not prev_published and not is_date_published(db, target_date):
            raise HTTPException(
                status_code=409,
                detail="현재 배포(공개) 중인 상태가 아닙니다.",
            )
        publish_count = max(1, prev_count)
        pub_map[date_key] = {
            **prev_meta,
            "published": False,
            "unpublished_at": now_str,
            "publish_count": publish_count,
        }
        # 배포 취소 시 확정/배포 상태를 DRAFT로 되돌려 수정 및 재확정->재배포 흐름을 따르도록 함
        db.query(Dispatch).filter(
            Dispatch.target_date == target_date,
            Dispatch.status.in_(("ANNOUNCED", "CONFIRMED")),
        ).update({"status": "DRAFT"}, synchronize_session=False)

    if row:
        row.value = pub_map
        flag_modified(row, "value")
    else:
        db.add(
            SystemConfig(
                key=DISPATCH_PUBLISHED_DATES_KEY,
                value=pub_map,
                description="날짜별 배차 공개(배포) 상태",
            )
        )
    db.commit()
    return {
        "target_date": date_key,
        "published": published,
        "is_reannounce": is_reannounce,
        "publish_count": publish_count,
        "meta": pub_map.get(date_key),
    }


def filter_custom_dispatch_rows(db: Session, target_date: date, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """백엔드 단일 진실 공급원(SSOT): 날짜 단위 공개 여부 및 예고 구간 정책으로 조회 가능 여부를 판정합니다."""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    settings = get_dispatch_settings(db)

    if target_date == today:
        if settings.get("confirm_d_day_always_open", True):
            return rows
        return rows if is_date_published(db, today) else []

    if target_date == tomorrow:
        if not settings.get("confirm_d1_require_announced", True):
            return rows
        return rows if is_date_published(db, tomorrow) else []

    # 미래(D+2+) 배차 예고는 verify_custom_preview_access()의 날짜 구간/일시정지 정책만으로 결정
    return rows


def get_dispatch_resources(db: Session) -> Dict[str, Any]:
    """배차 조율에 필요한 차량 풀, 기사 목록, 전역 설정을 반환합니다."""
    from domain.v1.dispatch.dispatch_builder import (
        _resolve_shared_data_path,
        load_vehicles_metadata,
    )

    vehicles_by_group = load_vehicles_metadata() or {}
    drivers_raw: Any = []
    drivers_path = _resolve_shared_data_path("drivers.json")
    if drivers_path:
        try:
            with open(drivers_path, "r", encoding="utf-8") as f:
                drivers_raw = json.load(f)
        except Exception:
            drivers_raw = []

    return {
        "vehicles_by_group": vehicles_by_group,
        "drivers": drivers_raw if isinstance(drivers_raw, list) else [],
        "settings": get_dispatch_settings(db),
    }


def announce_tomorrow_dispatch(
    db: Session,
    *,
    force: bool = False,
    trigger_user: Optional[User] = None,
) -> Dict[str, Any]:
    """명일(D+1) 배차를 일괄 확정(CONFIRMED)하고 인앱 알림 + 웹 푸시를 발송합니다."""
    from domain.v1.dispatch.dispatch_builder import (
        build_daily_dispatch_rows,
        query_active_routes_for_date,
    )
    from core.notify import safe_notify
    from domain.push.push_service import (
        is_push_domain_enabled,
        dispatch_push_async,
        send_push_to_app_users,
    )

    settings = get_dispatch_settings(db)
    now = _now_kst()
    today_str = now.date().isoformat()
    tomorrow = now.date() + timedelta(days=1)
    tomorrow_str = tomorrow.isoformat()

    # 🔒 [상태 머신 검증] 전날(D-1) 전체 노선 확정(CONFIRMED) 및 미배포 상태 검증
    state = get_dispatch_date_state(db, tomorrow)
    if state["published"]:
        if not force:
            return {"status": "already_published", "target_date": tomorrow_str, "updated_count": 0}
        raise HTTPException(
            status_code=409,
            detail="이미 배포(공개) 중인 명일 배차입니다. 재배포하려면 먼저 '배포 취소'를 실행해 주세요.",
        )
    if not state["confirmed"]:
        if not force:
            return {
                "status": "waiting_confirmation",
                "target_date": tomorrow_str,
                "confirmed_count": state["confirmed_count"],
                "total_count": state["total_count"],
            }
        raise HTTPException(
            status_code=400,
            detail=f"모든 노선의 명일 배차가 확정되어야 배포할 수 있습니다. (현재 확정: {state['confirmed_count']}/{state['total_count']})",
        )

    active_routes = query_active_routes_for_date(db, tomorrow)
    route_ids = [r["id"] for r in active_routes if isinstance(r, dict) and r.get("id")]

    updated_count = 0
    already_announced_all = True

    if route_ids:
        timetable_rows = (
            db.query(RouteTimetable)
            .filter(RouteTimetable.route_master_id.in_(route_ids))
            .all()
        )
        tt_ids = [t.id for t in timetable_rows]
        existing_map: Dict[int, Dispatch] = {}
        if tt_ids:
            existing_rows = (
                db.query(Dispatch)
                .filter(Dispatch.target_date == tomorrow, Dispatch.timetable_id.in_(tt_ids))
                .all()
            )
            existing_map = {d.timetable_id: d for d in existing_rows}

        for rid in route_ids:
            computed_rows = build_daily_dispatch_rows(db, tomorrow, rid)
            for cr in computed_rows:
                tid = cr.get("timetable_id")
                if not tid:
                    continue
                d_row = existing_map.get(tid)
                if d_row:
                    if d_row.status != "ANNOUNCED":
                        already_announced_all = False
                        d_row.status = "ANNOUNCED"
                        updated_count += 1
                else:
                    already_announced_all = False
                    new_row = Dispatch(
                        target_date=tomorrow,
                        timetable_id=tid,
                        driver_name=cr.get("driver_name"),
                        vehicle_no=cr.get("vehicle_no"),
                        start_time=cr.get("start_time"),
                        status="ANNOUNCED",
                        memo=cr.get("memo") or "",
                    )
                    db.add(new_row)
                    existing_map[tid] = new_row
                    updated_count += 1

        if not existing_map:
            already_announced_all = False

    if not force and settings.get("auto_announce_skip_if_confirmed", True) and already_announced_all and updated_count == 0:
        return {"status": "skipped_already_announced", "target_date": tomorrow_str, "updated_count": 0}

    db.commit()
    pub_res = set_date_published(db, tomorrow, True, mode="manual" if force else "auto")
    is_reannounce = bool(pub_res.get("is_reannounce", False))
    publish_count = int(pub_res.get("publish_count") or 1)

    # 자동/수동 고지 실행 이력 기록 (수동 배포가 예약된 자동 배포를 막지 않도록 분리)
    state_row = db.query(SystemConfig).filter(SystemConfig.key == DISPATCH_AUTO_ANNOUNCE_STATE_KEY).first()
    prev_val = dict(state_row.value) if (state_row and isinstance(state_row.value, dict)) else {}
    state_val = {
        **prev_val,
        "target_date": tomorrow_str,
        "ran_at": now.strftime("%Y-%m-%d %H:%M"),
    }
    if force:
        state_val["last_manual_date"] = today_str
        state_val["last_manual_at"] = now.strftime("%Y-%m-%d %H:%M")
    else:
        state_val["last_run_date"] = today_str
        state_val["last_auto_date"] = today_str
        state_val["last_auto_at"] = now.strftime("%Y-%m-%d %H:%M")
    if state_row:
        state_row.value = state_val
        flag_modified(state_row, "value")
    else:
        db.add(SystemConfig(key=DISPATCH_AUTO_ANNOUNCE_STATE_KEY, value=state_val, description="명일 배차 자동 고지 실행 이력"))
    db.commit()

    push_sent = False
    if settings.get("auto_announce_push", True):
        # 전체 활성 사용자 ID 조회 (dispatch 앱 접근 가능 대상)
        active_users = db.query(User).all()
        target_ids = [u.id for u in active_users if u.profile is None or u.profile.is_active is not False]
        min_rank = int(settings.get("announce_sender_min_rank", 4))
        sender = trigger_user or next((u for u in active_users if u.rank() >= min_rank), None)
        if is_reannounce:
            title_tpl = str(
                settings.get("reannounce_title_template")
                or DEFAULT_DISPATCH_SETTINGS["reannounce_title_template"]
            )
            body_tpl = str(
                settings.get("reannounce_body_template")
                or DEFAULT_DISPATCH_SETTINGS["reannounce_body_template"]
            )
        else:
            title_tpl = str(
                settings.get("auto_announce_title_template")
                or DEFAULT_DISPATCH_SETTINGS["auto_announce_title_template"]
            )
            body_tpl = str(
                settings.get("auto_announce_body_template")
                or DEFAULT_DISPATCH_SETTINGS["auto_announce_body_template"]
            )
        title = title_tpl.replace("{target_date}", tomorrow_str)
        msg = body_tpl.replace("{target_date}", tomorrow_str)
        if sender and target_ids:
            safe_notify(
                db=db,
                category="NOTIFICATION",
                title=title,
                message=msg,
                sender=sender,
                target_user_ids=target_ids,
                level=2,
                link="/v1/custom/dispatch",
                extra_payload={
                    "target_date": tomorrow_str,
                    "is_reannounce": is_reannounce,
                    "publish_count": publish_count,
                    "send_web_push": False,
                },
            )
        if is_push_domain_enabled(db, "dispatch_announce"):
            dispatch_push_async(
                send_push_to_app_users,
                app_id="dispatch",
                title=title,
                body=msg,
                url="/v1/custom/dispatch",
            )
        push_sent = True

    return {
        "status": "announced",
        "target_date": tomorrow_str,
        "updated_count": updated_count,
        "push_sent": push_sent,
        "is_reannounce": is_reannounce,
        "publish_count": publish_count,
    }


def check_and_run_auto_announce(db: Session) -> Dict[str, Any]:
    """
    1분 주기 크론에서 호출되어 설정된 자동 고지 시각(D-1 xx:yy) 이후에 명일 배차를 자동 공개/재공개합니다.
    - 이미 공개(published=True) 중인 날짜는 중복 실행하지 않습니다.
    - 공개 취소 후 수정·재확정(confirmed=True, was_published=True)된 경우에도 설정 시각 이후면
      자동 재공개 및 재공지 알림(is_reannounce=True)을 발송합니다.
    - 전 노선 확정 완료(confirmed=True) 상태일 때만 실행됩니다.
    """
    settings = get_dispatch_settings(db)
    if not settings.get("auto_announce_enabled", False):
        return {"status": "disabled"}

    now = _now_kst()
    now_hhmm = now.strftime("%H:%M")
    target_hhmm = str(settings.get("auto_announce_time") or "17:00")

    if now_hhmm < target_hhmm:
        return {"status": "waiting", "now": now_hhmm, "target": target_hhmm}

    tomorrow = now.date() + timedelta(days=1)
    state = get_dispatch_date_state(db, tomorrow)
    if state["published"]:
        return {"status": "already_published", "date": tomorrow.isoformat()}
    if not state["confirmed"]:
        return {
            "status": "waiting_confirmation",
            "date": tomorrow.isoformat(),
            "confirmed_count": state["confirmed_count"],
            "total_count": state["total_count"],
        }

    return announce_tomorrow_dispatch(db, force=False)


def _parse_hhmm_to_min(hhmm: Any) -> Optional[int]:
    s = str(hhmm or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 30 and 0 <= mn <= 59):
        return None
    return h * 60 + mn


def _calc_overlap_minutes(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    return max(0, hi - lo)


def _calc_night_minutes(start_min: int, end_min: int, morning_end_min: int, evening_start_min: int) -> int:
    if end_min <= start_min:
        return 0
    total = 0
    # 당일 아침 00:00 ~ morning_end_min
    total += _calc_overlap_minutes(start_min, end_min, 0, morning_end_min)
    # 당일 저녁 evening_start_min ~ 24:00 (1440)
    total += _calc_overlap_minutes(start_min, end_min, evening_start_min, 1440)
    # 자정 이후(익일 새벽 24:00 ~ 24:00 + morning_end_min)
    total += _calc_overlap_minutes(start_min, end_min, 1440, 1440 + morning_end_min)
    return total


def build_timetable_rotation_resolver(db: Session):
    """
    Dispatch.timetable_id(기준 슬롯)를 target_date 기준 실제 순환 로번(ref_t) 정보로
    변환하는 (resolve_fn, max_seq_by_route)를 반환합니다. (Redis 캐시 활용)
    """
    cached_bundle: Optional[Dict[str, Any]] = None
    if redis_client is not None:
        try:
            raw = redis_client.get(DISPATCH_TIMETABLE_ROTATION_CACHE_KEY)
            if raw:
                cached_bundle = json.loads(raw)
        except Exception:
            cached_bundle = None

    if cached_bundle is None:
        master_rows = db.query(
            RouteMaster.id, RouteMaster.start_date, RouteMaster.start_turn_seq
        ).all()
        master_info_raw = {
            str(rm_id): [rm_start_date.isoformat() if rm_start_date else None, rm_start_turn or 1]
            for rm_id, rm_start_date, rm_start_turn in master_rows
        }

        tt_rows = (
            db.query(
                RouteTimetable.id,
                RouteTimetable.route_master_id,
                RouteTimetable.route_name,
                RouteTimetable.seq,
                RouteTimetable.start_time,
                RouteTimetable.end_time,
                RouteTimetable.start_location,
                RouteTimetable.end_location,
            )
            .order_by(RouteTimetable.route_master_id, RouteTimetable.seq)
            .all()
        )
        timetables_by_rm_raw: Dict[str, List[Dict[str, Any]]] = {}
        index_by_tt_id_raw: Dict[str, List[Any]] = {}
        max_seq_raw: Dict[str, int] = {}
        for tt_id, rm_id, r_name, tt_seq, tt_start, tt_end, s_loc, e_loc in tt_rows:
            if rm_id is None:
                continue
            rm_key = str(rm_id)
            bucket = timetables_by_rm_raw.setdefault(rm_key, [])
            index_by_tt_id_raw[str(tt_id)] = [rm_key, len(bucket)]
            bucket.append({
                "route_master_id": rm_id,
                "route_name": r_name or "-",
                "seq": tt_seq or 0,
                "start_time": tt_start or "",
                "end_time": tt_end or "",
                "start_location": s_loc or "-",
                "end_location": e_loc or "-",
            })
            if tt_seq is not None:
                prev_max = max_seq_raw.get(rm_key)
                if prev_max is None or tt_seq > prev_max:
                    max_seq_raw[rm_key] = tt_seq

        start_offset_raw: Dict[str, int] = {}
        for rm_key, tts in timetables_by_rm_raw.items():
            _, s_turn = master_info_raw.get(rm_key, [None, 1])
            start_offset_raw[rm_key] = next(
                (idx for idx, item in enumerate(tts) if item["seq"] == s_turn),
                0,
            )

        cached_bundle = {
            "master_info": master_info_raw,
            "timetables_by_rm": timetables_by_rm_raw,
            "index_by_tt_id": index_by_tt_id_raw,
            "max_seq_by_route": max_seq_raw,
            "start_offset_by_rm": start_offset_raw,
        }
        if redis_client is not None:
            try:
                redis_client.set(
                    DISPATCH_TIMETABLE_ROTATION_CACHE_KEY,
                    json.dumps(cached_bundle, ensure_ascii=False),
                    ex=DISPATCH_TIMETABLE_ROTATION_TTL,
                )
            except Exception:
                pass

    master_info: Dict[str, tuple] = {}
    for rm_key, val in (cached_bundle.get("master_info") or {}).items():
        s_date = date.fromisoformat(val[0]) if val and val[0] else None
        master_info[rm_key] = (s_date, val[1] if val else 1)

    timetables_by_rm = cached_bundle.get("timetables_by_rm") or {}
    index_by_tt_id = cached_bundle.get("index_by_tt_id") or {}
    start_offset_by_rm = cached_bundle.get("start_offset_by_rm") or {}
    max_seq_by_route: Dict[int, int] = {
        int(k): v for k, v in (cached_bundle.get("max_seq_by_route") or {}).items()
    }

    def resolve(tt_id: int, d_date: date) -> Optional[Dict[str, Any]]:
        tt_meta = index_by_tt_id.get(str(tt_id))
        if not tt_meta:
            return None
        rm_key, base_idx = tt_meta
        tts = timetables_by_rm.get(rm_key) or []
        if not tts:
            return None
        rm_start_date, _ = master_info.get(rm_key, (d_date, 1))
        delta_days = max(0, (d_date - rm_start_date).days) if rm_start_date else 0
        start_offset = start_offset_by_rm.get(rm_key, 0)
        return tts[(base_idx + delta_days + start_offset) % len(tts)]

    return resolve, max_seq_by_route


def build_driver_work_stats(db: Session, target_date: date) -> Dict[str, Any]:
    """
    조회일(target_date) 기준 어제(target_date - 1일)까지의 기사별 운행 통계(월간/주간/야간/직전종료)와
    당일 결근·병가·징계 여부를 집계합니다.
    """
    settings = get_dispatch_settings(db)

    cache_key: Optional[str] = None
    if redis_client is not None:
        try:
            sig_payload = json.dumps(
                {
                    "weekly_basis": settings.get("weekly_basis"),
                    "min_rest_hours": settings.get("min_rest_hours"),
                    "night_metric_mode": settings.get("night_metric_mode"),
                    "night_route_turn_rules": settings.get("night_route_turn_rules"),
                    "night_morning_end": settings.get("night_morning_end"),
                    "night_evening_start": settings.get("night_evening_start"),
                    "stats_include_draft": settings.get("stats_include_draft"),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            sig_hash = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()[:12]
            cache_key = f"{DISPATCH_STATS_CACHE_PREFIX}{target_date.isoformat()}:{sig_hash}"
            cached_raw = redis_client.get(cache_key)
            if cached_raw:
                return json.loads(cached_raw)
        except Exception:
            cache_key = None

    yesterday = target_date - timedelta(days=1)
    month_start = target_date.replace(day=1)

    if settings.get("weekly_basis") == "rolling_7d":
        week_start = target_date - timedelta(days=7)
    else:
        # 달력 주(일~토) 기준 이번 주 일요일
        days_since_sunday = (target_date.weekday() + 1) % 7
        week_start = target_date - timedelta(days=days_since_sunday)

    query_start = min(month_start, week_start, yesterday)

    resolve_tt, max_seq_by_route = build_timetable_rotation_resolver(db)

    q = (
        db.query(
            Dispatch.driver_name,
            Dispatch.target_date,
            Dispatch.start_time,
            Dispatch.timetable_id,
        )
        .filter(
            Dispatch.target_date >= query_start,
            Dispatch.target_date <= yesterday,
            Dispatch.driver_name.isnot(None),
            Dispatch.driver_name != "",
        )
    )
    if not settings.get("stats_include_draft", True):
        q = q.filter(Dispatch.status.in_(("CONFIRMED", "ANNOUNCED")))

    rows = q.all()

    night_route_rules = [
        (r["route_keyword"], set(r["turn_seqs"]))
        for r in (settings.get("night_route_turn_rules") or [])
        if r.get("route_keyword") and r.get("turn_seqs")
    ]
    morning_end_min = _parse_hhmm_to_min(settings.get("night_morning_end", "06:00")) or 360
    evening_start_min = _parse_hhmm_to_min(settings.get("night_evening_start", "21:00")) or 1260
    min_rest_min = int(settings.get("min_rest_hours", 8)) * 60

    stats_map: Dict[str, Dict[str, Any]] = {}

    def _ensure(name: str) -> Dict[str, Any]:
        if name not in stats_map:
            stats_map[name] = {
                "name": name,
                "month_dates": set(),
                "week_dates": set(),
                "month_work_minutes": 0,
                "month_night_count": 0,
                "month_night_minutes": 0,
                "prev_end_min": None,
                "prev_end_time": None,
                "worked_yesterday": False,
                "last_work_date": None,
                "dayoff_type": None,
                "dayoff_status": None,
                "is_disciplined": False,
            }
        return stats_map[name]

    for d_name_raw, d_date, disp_start_time, tt_id in rows:
        d_name = str(d_name_raw or "").strip()
        if not d_name:
            continue
        ref_t = resolve_tt(tt_id, d_date)
        if not ref_t:
            continue
        rm_id = ref_t["route_master_id"]
        tt_seq = ref_t["seq"]
        tt_start_time = ref_t["start_time"]
        tt_end_time = ref_t["end_time"]

        entry = _ensure(d_name)

        s_min = _parse_hhmm_to_min(disp_start_time or tt_start_time)
        e_min = _parse_hhmm_to_min(tt_end_time)
        if s_min is not None and e_min is not None:
            if e_min < s_min:
                e_min += 1440
            dur = max(0, e_min - s_min)
        else:
            dur = 0

        if month_start <= d_date <= yesterday:
            entry["month_dates"].add(d_date)
            entry["month_work_minutes"] += dur

            tt_route_name = ref_t.get("route_name") or ""
            matched_rule_seqs = next(
                (seqs for kw, seqs in night_route_rules if kw in tt_route_name),
                None,
            )
            if matched_rule_seqs is not None and tt_seq in matched_rule_seqs:
                entry["month_night_count"] += 1

            if s_min is not None and e_min is not None:
                entry["month_night_minutes"] += _calc_night_minutes(
                    s_min, e_min, morning_end_min, evening_start_min
                )

        if week_start <= d_date <= yesterday:
            entry["week_dates"].add(d_date)

        if d_date <= yesterday:
            if entry["last_work_date"] is None or d_date > entry["last_work_date"]:
                entry["last_work_date"] = d_date

        if d_date == yesterday:
            entry["worked_yesterday"] = True
            if e_min is not None and (entry["prev_end_min"] is None or e_min > entry["prev_end_min"]):
                entry["prev_end_min"] = e_min
                hh = (e_min % 1440) // 60
                mm = e_min % 60
                entry["prev_end_time"] = f"{hh:02d}:{mm:02d}"

    # 당일 결근·병가(DayOff) 매칭
    dayoff_rows = (
        db.query(DayOff)
        .options(joinedload(DayOff.user))
        .filter(
            DayOff.date == target_date,
            DayOff.is_deleted == False,
            DayOff.status.notin_(["REJECTED", "CANCELLED"]),
        )
        .all()
    )
    for do in dayoff_rows:
        u = do.user
        if not u:
            continue
        for cand in {getattr(u, "real_name", None), getattr(u, "username", None)}:
            if cand and str(cand).strip():
                entry = _ensure(str(cand).strip())
                entry["dayoff_type"] = do.type
                entry["dayoff_status"] = do.status

    # 직렬화 (Set 제거 및 휴식 가능 시각 계산)
    result: Dict[str, Any] = {}
    for name, st in stats_map.items():
        prev_end = st["prev_end_min"]
        earliest_today_min: Optional[int] = None
        earliest_time_str: Optional[str] = None
        if prev_end is not None:
            # 어제 기준 분(prev_end) + min_rest_min -> 오늘 자정(1440) 기준 차감
            avail_from_midnight = (prev_end + min_rest_min) - 1440
            if avail_from_midnight > 0:
                earliest_today_min = avail_from_midnight
                eh = (avail_from_midnight % 1440) // 60
                em = avail_from_midnight % 60
                earliest_time_str = f"{eh:02d}:{em:02d}"
            else:
                earliest_today_min = 0
                earliest_time_str = "00:00"

        if st["worked_yesterday"]:
            consecutive_off_days = 0
        elif st["last_work_date"] is not None:
            consecutive_off_days = max(1, (target_date - st["last_work_date"]).days - 1)
        else:
            consecutive_off_days = max(3, (target_date - query_start).days)

        result[name] = {
            "name": name,
            "month_work_days": len(st["month_dates"]),
            "week_work_days": len(st["week_dates"]),
            "month_work_minutes": st["month_work_minutes"],
            "month_night_count": st["month_night_count"],
            "month_night_minutes": st["month_night_minutes"],
            "prev_end_time": st["prev_end_time"],
            "worked_yesterday": st["worked_yesterday"],
            "consecutive_off_days": consecutive_off_days,
            "earliest_today_min": earliest_today_min,
            "earliest_available_time": earliest_time_str,
            "dayoff_type": st["dayoff_type"],
            "dayoff_status": st["dayoff_status"],
            "is_disciplined": st["is_disciplined"],
        }

    # 당일(target_date) 이미 배정된 기사 목록 (단일 노선 조회 시 타 노선 배정자 제외용)
    assigned_today_rows = (
        db.query(Dispatch.driver_name)
        .filter(
            Dispatch.target_date == target_date,
            Dispatch.driver_name.isnot(None),
            Dispatch.driver_name != "",
        )
        .distinct()
        .all()
    )
    assigned_today_drivers = sorted(
        {str(name).strip() for (name,) in assigned_today_rows if str(name or "").strip()}
    )

    payload = {
        "target_date": target_date.isoformat(),
        "stats": result,
        "assigned_today_drivers": assigned_today_drivers,
    }
    if cache_key and redis_client is not None:
        try:
            redis_client.set(cache_key, json.dumps(payload, ensure_ascii=False), ex=DISPATCH_STATS_CACHE_TTL)
        except Exception:
            pass
    return payload


def get_driver_dispatch_detail(db: Session, driver_name: str, target_date: date) -> Dict[str, Any]:
    """
    기사 상세 모달용 다중 테이블 조회:
    - 당일/명일 노선 투입 여부 (Dispatch + RouteTimetable 순환 보정)
    - 최근 30일 노선 운행 내역 및 이번 달 노선별 분포
    - 결근계·병가 작성 내역 (DayOff + User)
    """
    clean_name = str(driver_name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="기사명을 입력해 주세요.")

    resolve_tt, _ = build_timetable_rotation_resolver(db)
    month_start = target_date.replace(day=1)
    recent_start = min(month_start, target_date - timedelta(days=30))
    tomorrow = target_date + timedelta(days=1)

    disp_rows = (
        db.query(
            Dispatch.target_date,
            Dispatch.timetable_id,
            Dispatch.vehicle_no,
            Dispatch.start_time,
            Dispatch.status,
            Dispatch.memo,
        )
        .filter(
            Dispatch.driver_name == clean_name,
            Dispatch.target_date >= recent_start,
            Dispatch.target_date <= tomorrow,
        )
        .order_by(Dispatch.target_date.desc())
        .all()
    )

    today_assignments: List[Dict[str, Any]] = []
    tomorrow_assignments: List[Dict[str, Any]] = []
    recent_dispatches: List[Dict[str, Any]] = []
    route_counts: Dict[str, int] = {}

    for d_date, tt_id, vno, disp_start, status_val, memo_val in disp_rows:
        ref_t = resolve_tt(tt_id, d_date) if tt_id else None
        item = {
            "target_date": d_date.isoformat(),
            "route_name": ref_t["route_name"] if ref_t else "-",
            "seq": ref_t["seq"] if ref_t else 0,
            "vehicle_no": vno or "-",
            "start_time": disp_start or (ref_t["start_time"] if ref_t else ""),
            "end_time": ref_t["end_time"] if ref_t else "",
            "status": status_val or "DRAFT",
            "memo": memo_val or "",
        }
        if d_date == target_date:
            today_assignments.append(item)
        elif d_date == tomorrow:
            tomorrow_assignments.append(item)
        else:
            if len(recent_dispatches) < 12:
                recent_dispatches.append(item)
            if month_start <= d_date < target_date and item["route_name"] != "-":
                route_counts[item["route_name"]] = route_counts.get(item["route_name"], 0) + 1

    route_breakdown = [
        {"route_name": rname, "count": cnt}
        for rname, cnt in sorted(route_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    # 결근계 · 병가 작성 내역 (최근 60일 ~ 향후 30일)
    matched_users = (
        db.query(User.id)
        .filter(or_(User.real_name == clean_name, User.username == clean_name))
        .all()
    )
    user_ids = [u_id for (u_id,) in matched_users]
    dayoff_history: List[Dict[str, Any]] = []
    if user_ids:
        do_rows = (
            db.query(DayOff)
            .filter(
                DayOff.user_id.in_(user_ids),
                DayOff.is_deleted == False,
                DayOff.date >= target_date - timedelta(days=60),
                DayOff.date <= target_date + timedelta(days=30),
            )
            .order_by(DayOff.date.desc())
            .limit(15)
            .all()
        )
        for do in do_rows:
            dayoff_history.append({
                "id": do.id,
                "date": do.date.isoformat() if do.date else "",
                "type": do.type,
                "status": do.status,
                "memo": do.memo or "",
                "create_date": do.create_date.strftime("%Y-%m-%d %H:%M") if do.create_date else "",
            })

    return {
        "driver_name": clean_name,
        "target_date": target_date.isoformat(),
        "today_assignments": today_assignments,
        "tomorrow_assignments": tomorrow_assignments,
        "recent_dispatches": recent_dispatches,
        "route_breakdown": route_breakdown,
        "dayoff_history": dayoff_history,
    }
