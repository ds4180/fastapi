from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from redis_config import get_redis
from models import User, UserProfile, DayOff, Dispatch, RouteTimetable, RouteMaster
from datetime import datetime
import json
import logging

logger = logging.getLogger("group_router")

router = APIRouter(prefix="/v1/admin/groups", tags=["Admin Groups Management"])

# Redis Key Constants
KEY_DATA = "group:data:" # group:data:{name} -> Set of user_ids
KEY_META = "group:metadata" # group:metadata -> Hash {name: metadata_json}


def calculate_and_refresh_dynamic_groups(db: Session, rd) -> dict:
    """
    [실 비즈니스 동적 그룹 연산 엔진]
    - 오늘 휴무자 (today_dayoff): DayOff 승인된 인원
    - 오늘 근무자 (today_working): 전체 활성 인원 - 오늘 휴무자
    - 시내버스 운전자 (bus_city): primary/secondary 소속 '시내' 포함 인원
    - 시외버스 운전자 (bus_intercity): primary/secondary 소속 '시외' 포함 인원
    - 오늘 배차 노선별 기사 (dispatch_today_{route}): 당일 CONFIRMED 배차 노선별 기사
    """
    today = datetime.now().date()
    refreshed_groups = {}

    # 1. 오늘 승인된 휴무자 (today_dayoff)
    dayoff_records = db.query(DayOff.user_id).filter(
        DayOff.date == today,
        DayOff.status == "APPROVED",
        DayOff.is_deleted == False
    ).all()
    today_dayoff_uids = [str(r[0]) for r in dayoff_records]
    _save_group(rd, "today_dayoff", today_dayoff_uids, "dynamic", "오늘 승인된 휴무/연차 대상자")
    refreshed_groups["today_dayoff"] = len(today_dayoff_uids)

    # 2. 오늘 실제 근무/운행 인원 (today_working = 전체 활성 사용자 - 오늘 휴무자)
    active_users = db.query(User.id).join(UserProfile, User.id == UserProfile.user_id).filter(
        UserProfile.is_active == True
    ).all()
    dayoff_set = set(today_dayoff_uids)
    today_working_uids = [str(u[0]) for u in active_users if str(u[0]) not in dayoff_set]
    _save_group(rd, "today_working", today_working_uids, "dynamic", "오늘 실제 근무/운행 중인 인원 (휴무자 제외)")
    refreshed_groups["today_working"] = len(today_working_uids)

    # 3. 소속 그룹 기반: 시내버스 / 시외버스 운전원
    all_profiles = db.query(User.id, UserProfile.primary_group, UserProfile.secondary_groups).join(
        UserProfile, User.id == UserProfile.user_id
    ).filter(UserProfile.is_active == True).all()

    bus_city_uids = []
    bus_intercity_uids = []
    for uid, p_grp, s_grps in all_profiles:
        p_str = p_grp or ""
        s_list = s_grps if isinstance(s_grps, list) else []
        all_grp_texts = [p_str] + [str(g) for g in s_list]
        if any("시내" in g for g in all_grp_texts):
            bus_city_uids.append(str(uid))
        if any("시외" in g for g in all_grp_texts):
            bus_intercity_uids.append(str(uid))

    _save_group(rd, "bus_city", bus_city_uids, "dynamic", "시내버스 전담 운전원")
    refreshed_groups["bus_city"] = len(bus_city_uids)

    _save_group(rd, "bus_intercity", bus_intercity_uids, "dynamic", "시외버스 전담 운전원")
    refreshed_groups["bus_intercity"] = len(bus_intercity_uids)

    # 4. 오늘 배차 노선별 기사 그룹 (dispatch_today_{route_name})
    today_dispatches = db.query(
        RouteMaster.route_name,
        Dispatch.driver_name
    ).join(
        RouteTimetable, Dispatch.timetable_id == RouteTimetable.id
    ).join(
        RouteMaster, RouteTimetable.route_master_id == RouteMaster.id
    ).filter(
        Dispatch.target_date == today,
        Dispatch.status == "CONFIRMED",
        Dispatch.driver_name.is_not(None)
    ).all()

    driver_names = list({d[1] for d in today_dispatches if d[1]})
    user_map = {}
    if driver_names:
        matched_users = db.query(User.id, User.real_name, User.username).filter(
            (User.real_name.in_(driver_names)) | (User.username.in_(driver_names))
        ).all()
        for u in matched_users:
            if u.real_name:
                user_map[u.real_name] = str(u.id)
            user_map[u.username] = str(u.id)

    route_drivers = {}
    for route_name, driver_name in today_dispatches:
        uid = user_map.get(driver_name)
        if uid:
            clean_route = route_name.replace(" ", "_").replace("/", "_")
            if clean_route not in route_drivers:
                route_drivers[clean_route] = set()
            route_drivers[clean_route].add(uid)

    for route_name, uids in route_drivers.items():
        grp_name = f"dispatch_today_{route_name}"
        _save_group(rd, grp_name, list(uids), "dynamic", f"오늘 {route_name} 노선 배정 운행 기사")
        refreshed_groups[grp_name] = len(uids)

    logger.info(f"✨ 동적 타겟 그룹 연산 완료: {refreshed_groups}")
    return refreshed_groups


@router.get("")
def get_all_groups(rd=Depends(get_redis)):
    """현재 생성된 모든 그룹(수동, 다이나믹, 복합) 목록 조회"""
    metas = rd.hgetall(KEY_META)
    result = []
    for name, meta_str in metas.items():
        meta = json.loads(meta_str)
        meta["count"] = rd.scard(f"{KEY_DATA}{name}")
        result.append(meta)
    return result

@router.post("/manual")
def create_manual_group(name: str = Body(...), user_ids: list[int] = Body(...), rd=Depends(get_redis)):
    """수동 그룹 생성"""
    target_key = f"{KEY_DATA}{name}"
    rd.delete(target_key)
    if user_ids:
        rd.sadd(target_key, *[str(uid) for uid in user_ids])
    
    meta = {"name": name, "type": "manual", "desc": "관리자 수동 지정 그룹"}
    rd.hset(KEY_META, name, json.dumps(meta))
    return {"message": "Success", "count": len(user_ids)}

@router.post("/dynamic/refresh")
def refresh_dynamic_groups(db: Session = Depends(get_db), rd=Depends(get_redis)):
    """실 비즈니스 다이나믹 그룹 강제 연산 및 갱신"""
    results = calculate_and_refresh_dynamic_groups(db, rd)
    return {"message": "Dynamic groups refreshed", "results": results}


@router.post("/combine")
def combine_groups(
    new_name: str = Body(...),
    op: str = Body(..., description="INTERSECT | DIFF | UNION"),
    base_group: str = Body(...),
    target_groups: list[str] = Body(...),
    rd=Depends(get_redis)
):
    """그룹간 집합 연산 (교집합, 차집합, 합집합)"""
    keys = [f"{KEY_DATA}{base_group}"] + [f"{KEY_DATA}{g}" for g in target_groups]
    dest_key = f"{KEY_DATA}{new_name}"
    
    if op == "INTERSECT":
        rd.sinterstore(dest_key, *keys)
    elif op == "DIFF":
        rd.sdiffstore(dest_key, *keys)
    elif op == "UNION":
        rd.sunionstore(dest_key, *keys)
    else:
        raise HTTPException(status_code=400, detail="Invalid operation")

    meta = {"name": new_name, "type": "combined", "desc": f"{op} 연산으로 생성된 그룹", "op": op, "parents": [base_group] + target_groups}
    rd.hset(KEY_META, new_name, json.dumps(meta))
    return {"name": new_name, "count": rd.scard(dest_key)}

def _save_group(rd, name, uids, gtype, desc):
    key = f"{KEY_DATA}{name}"
    rd.delete(key)
    if uids:
        rd.sadd(key, *uids)
    meta = {"name": name, "type": gtype, "desc": desc}
    rd.hset(KEY_META, name, json.dumps(meta))

@router.delete("/{name}")
def delete_group(name: str, rd=Depends(get_redis)):
    """특정 그룹 삭제 (데이터 및 메타데이터 제거)"""
    rd.delete(f"{KEY_DATA}{name}")
    rd.hdel(KEY_META, name)
    return {"message": "Success"}
