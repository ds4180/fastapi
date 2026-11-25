"""
============================================================================
[차량 배차 로테이션 빌더 & 공용 메타데이터 로더 (domain/v1/dispatch/dispatch_builder.py)]
============================================================================
- 기존 admin_router.py에 위치하여 역방향 참조(Service -> Router)를 유발하던
  메타데이터 로더 및 일일 배차·작업률 계산 로직을 서비스 계층으로 분리했습니다.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models
from models import RouteMaster, RouteTimetable

DEFAULT_VEHICLES_METADATA = {
    "121/122": ["3164", "3118", "3103", "3145"],
    "291/292/293": [
        "3139", "3121", "3128", "3151", "3146", "3137",
        "3125", "3111", "3158", "3160", "3150", "3144",
    ],
}


def _resolve_shared_data_path(filename: str) -> Optional[str]:
    candidates = [
        f"/app/shared_data/{filename}",
        f"/app/data/{filename}",
        f"/home/lee/uv-code/svelte5/src/lib/data/{filename}",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def load_drivers_metadata():
    """Svelte 프론트엔드의 drivers.json 파일을 읽어서 기사 메타데이터를 구조화합니다."""
    try:
        path = _resolve_shared_data_path("drivers.json")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                drivers = json.load(f)
                role_map = {}
                vehicle_map = {}
                vehicle_drivers = {}
                for d in drivers:
                    name = d.get("name")
                    role = d.get("role")
                    v_no = d.get("vehicle_no")
                    if name:
                        name_stripped = name.strip()
                        role_map[name_stripped] = role
                        if v_no:
                            vehicle_map[name_stripped] = v_no
                            if v_no not in vehicle_drivers:
                                vehicle_drivers[v_no] = {}
                            vehicle_drivers[v_no][role] = name_stripped
                return role_map, vehicle_map, vehicle_drivers
        return {}, {}, {}
    except Exception as e:
        print(f"⚠️ [load_drivers_metadata] Error: {e}")
        return {}, {}, {}


def load_vehicles_metadata():
    """Svelte 프론트엔드의 vehicles.json 파일을 읽어서 노선별 차량 풀을 가져옵니다."""
    try:
        path = _resolve_shared_data_path("vehicles.json")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                vehicles = data.get("vehicles", {})
                if vehicles:
                    return vehicles
        return DEFAULT_VEHICLES_METADATA
    except Exception as e:
        print(f"⚠️ [load_vehicles_metadata] Error: {e}")
        return DEFAULT_VEHICLES_METADATA


def query_active_routes_for_date(db: Session, target_date: date) -> List[dict]:
    """지정된 날짜(target_date) 기준 운행 중인 노선 마스터 목록을 반환합니다."""
    masters = (
        db.query(RouteMaster)
        .filter(
            RouteMaster.start_date <= target_date,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= target_date),
        )
        .order_by(RouteMaster.route_name.asc())
        .all()
    )

    return [
        {
            "id": m.id,
            "route_name": m.route_name,
            "route_type": m.route_type,
            "start_date": str(m.start_date),
            "end_date": str(m.end_date) if m.end_date else None,
            "vehicle_count": m.vehicle_count,
            "version": m.version,
            "is_regular_duty": m.is_regular_duty,
        }
        for m in masters
    ]


def build_dispatch_work_rates(db: Session, base_date: date, days: int = 10) -> List[dict]:
    """D+1 ~ D+days 기간의 일별 전체 배차 작업률(%)을 계산합니다."""
    days = max(1, min(days, 30))
    d_start = base_date + timedelta(days=1)
    d_end = base_date + timedelta(days=days)

    masters = (
        db.query(RouteMaster)
        .filter(
            RouteMaster.start_date <= d_end,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= d_start),
        )
        .all()
    )

    master_ids = [m.id for m in masters]
    master_to_tids: dict[int, set[int]] = {}
    all_tids: list[int] = []
    if master_ids:
        timetables = (
            db.query(RouteTimetable.id, RouteTimetable.route_master_id)
            .filter(RouteTimetable.route_master_id.in_(master_ids))
            .all()
        )
        for tid, mid in timetables:
            master_to_tids.setdefault(mid, set()).add(tid)
            all_tids.append(tid)

    assigned_by_date: dict[date, set[int]] = {}
    if all_tids:
        dispatches = (
            db.query(
                models.Dispatch.target_date,
                models.Dispatch.timetable_id,
                models.Dispatch.driver_name,
            )
            .filter(
                models.Dispatch.target_date >= d_start,
                models.Dispatch.target_date <= d_end,
                models.Dispatch.timetable_id.in_(all_tids),
            )
            .all()
        )
        for t_date, tid, driver_name in dispatches:
            if driver_name and driver_name.strip():
                assigned_by_date.setdefault(t_date, set()).add(tid)

    items: List[dict] = []
    for offset in range(1, days + 1):
        target_d = base_date + timedelta(days=offset)
        active_tids: set[int] = set()
        for m in masters:
            if m.start_date <= target_d and (m.end_date is None or m.end_date >= target_d):
                active_tids.update(master_to_tids.get(m.id, set()))

        total = len(active_tids)
        assigned = len(active_tids & assigned_by_date.get(target_d, set()))
        rate = round((assigned / total) * 100, 1) if total > 0 else 0.0
        items.append(
            {
                "offset": offset,
                "label": f"D+{offset}",
                "date": str(target_d),
                "assigned": assigned,
                "total": total,
                "rate": rate,
            }
        )

    has_real_dispatch = any(item["assigned"] > 0 for item in items)
    if not has_real_dispatch:
        mock_rates = [100.0, 95.0, 88.0, 76.0, 64.0, 52.0, 40.0, 28.0, 15.0, 5.0]
        for idx, item in enumerate(items):
            sample_rate = mock_rates[idx % len(mock_rates)]
            sample_total = item["total"] if item["total"] > 0 else 20
            item["total"] = sample_total
            item["assigned"] = round(sample_total * sample_rate / 100.0)
            item["rate"] = round((item["assigned"] / sample_total) * 100, 1)
            item["is_mock"] = True
    else:
        for item in items:
            item["is_mock"] = False

    return items


def build_daily_dispatch_rows(db: Session, target_date: date, route_master_id: int) -> List[dict]:
    """지정된 날짜와 노선 마스터 ID에 해당하는 일일 배차 행 목록을 계산해 반환합니다."""
    master = db.query(RouteMaster).filter(RouteMaster.id == route_master_id).first()
    if not master:
        raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")

    timetables = (
        db.query(RouteTimetable)
        .filter(RouteTimetable.route_master_id == route_master_id)
        .order_by(RouteTimetable.seq.asc())
        .all()
    )

    if not timetables:
        return []

    N = len(timetables)
    delta_days = max(0, (target_date - master.start_date).days)
    start_turn_seq = getattr(master, "start_turn_seq", 1) or 1
    start_offset = next((idx for idx, tt in enumerate(timetables) if tt.seq == start_turn_seq), 0)

    from domain.v1.dispatch.dispatch_service import get_dispatch_settings, resolve_route_fleet

    load_drivers_metadata()
    vehicles_dict = load_vehicles_metadata()
    dispatch_cfg = get_dispatch_settings(db)
    target_fleet = resolve_route_fleet(
        master.route_name or "",
        vehicles_dict,
        dispatch_cfg.get("route_fleet_rules"),
    )

    timetable_ids = [t.id for t in timetables]

    def _load_dispatch_map(d_date: date) -> dict:
        rows = (
            db.query(models.Dispatch)
            .filter(
                models.Dispatch.target_date == d_date,
                models.Dispatch.timetable_id.in_(timetable_ids),
            )
            .all()
        )
        return {row.timetable_id: row for row in rows}

    dispatch_map = _load_dispatch_map(target_date)
    tomorrow_map = _load_dispatch_map(target_date + timedelta(days=1))
    yesterday_map = _load_dispatch_map(target_date - timedelta(days=1))

    result = []
    for i, t in enumerate(timetables):
        ref_t = timetables[(i + delta_days + start_offset) % N]
        ref_t_yesterday = timetables[(i + delta_days + start_offset - 1) % N]
        ref_t_tomorrow = timetables[(i + delta_days + start_offset + 1) % N]

        is_yesterday_regular_duty = ref_t_yesterday.is_regular_duty
        is_tomorrow_regular_duty = ref_t_tomorrow.is_regular_duty

        yesterday_disp = yesterday_map.get(t.id)
        yesterday_driver_name = (
            yesterday_disp.driver_name if (yesterday_disp and yesterday_disp.driver_name) else None
        )

        d = dispatch_map.get(t.id)
        if d is not None:
            driver_name = d.driver_name or ""
            is_inherited = False
        elif is_yesterday_regular_duty and yesterday_driver_name:
            driver_name = yesterday_driver_name
            is_inherited = True
        else:
            driver_name = ""
            is_inherited = False

        default_vehicle = target_fleet[i] if i < len(target_fleet) else ""
        vehicle_no = d.vehicle_no if (d and d.vehicle_no) else default_vehicle

        td_d = tomorrow_map.get(t.id)
        if td_d and td_d.driver_name and td_d.driver_name.strip():
            tomorrow_driver_name = td_d.driver_name
            is_tomorrow_inherited = False
        elif ref_t.is_regular_duty and driver_name and driver_name.strip():
            tomorrow_driver_name = driver_name
            is_tomorrow_inherited = True
        else:
            tomorrow_driver_name = ""
            is_tomorrow_inherited = False

        result.append(
            {
                "id": d.id if d else None,
                "timetable_id": t.id,
                "seq": ref_t.seq,
                "start_time": (d.start_time if d else None) or ref_t.start_time,
                "end_time": ref_t.end_time,
                "start_location": ref_t.start_location,
                "end_location": ref_t.end_location,
                "driver_name": driver_name,
                "tomorrow_driver_name": tomorrow_driver_name,
                "yesterday_driver_name": yesterday_driver_name,
                "vehicle_no": vehicle_no,
                "status": d.status if d else "DRAFT",
                "memo": (d.memo if d else "") or "",
                "is_regular_duty": ref_t.is_regular_duty,
                "is_tomorrow_regular_duty": is_tomorrow_regular_duty,
                "is_yesterday_regular_duty": is_yesterday_regular_duty,
                "is_inherited": is_inherited,
                "is_tomorrow_inherited": is_tomorrow_inherited,
            }
        )

    return result
