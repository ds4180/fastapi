"""
============================================================================
[동적 타겟 그룹 및 Redis 그룹 비즈니스 서비스 (domain/system/group_service.py)]
============================================================================

💡 이 파일의 역할:
HTTP 라우터(`group_router.py`)에 섞여 있던 '실 비즈니스 동적 그룹 연산' 및
Redis 타겟팅 그룹(알림/메시징 발송 대상) 관리 로직을 순수 서비스 모듈로 캡슐화합니다.

🌟 아키텍처 이점:
1. 백그라운드 태스크 워커(`task_worker.py`)가 HTTP 라우터를 역임포트하던 기형적 결합(Smuggling)을 완벽히 해소합니다.
2. 비즈니스 3계층 아키텍처(Router -> Service -> Repository)를 준수합니다.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from models import User, UserProfile, DayOff, Dispatch, RouteTimetable, RouteMaster

logger = logging.getLogger("system.group_service")

# 📌 Redis 타겟 그룹 네임스페이스 키 상수 및 안전 TTL (STD-SYS-009 메모리 고아 방어)
KEY_DATA = "group:data:"      # group:data:{name} -> Set of user_ids
KEY_META = "group:metadata"   # group:metadata -> Hash {name: metadata_json}

DEFAULT_TTL_DYNAMIC = 172800   # 48시간 (2일) - 매일 갱신되는 실시간 동적 그룹
DEFAULT_TTL_MANUAL = 2592000   # 30일 - 관리자 수동 지정 그룹의 안전 수명주기
DEFAULT_TTL_COMBINED = 2592000 # 30일 - 집합 연산 결과 그룹의 안전 수명주기


def save_redis_group(rd, name: str, uids: List[str], gtype: str, desc: str, ttl_seconds: Optional[int] = None):
    """
    [Redis 타겟 그룹 저장 헬퍼 (전체 TTL 100% 강제 적용)]
    - uids 집합을 Redis Set에 저장합니다.
    - 메타데이터를 KEY_META 해시에 등록합니다.
    - 메모리 무한 잠식을 방지하기 위해 dynamic(48시간), manual(30일), combined(30일) 모두 안전 TTL을 강제합니다.
    """
    key = f"{KEY_DATA}{name}"
    rd.delete(key)
    effective_ttl = ttl_seconds
    if effective_ttl is None:
        if gtype == "dynamic":
            effective_ttl = DEFAULT_TTL_DYNAMIC
        elif gtype == "manual":
            effective_ttl = DEFAULT_TTL_MANUAL
        else:
            effective_ttl = DEFAULT_TTL_COMBINED

    if uids:
        rd.sadd(key, *uids)
        rd.expire(key, effective_ttl)
    else:
        # 빈 그룹이어도 만료 설정
        rd.expire(key, effective_ttl)

    now_iso = datetime.now().isoformat()
    created_at = now_iso
    existing_raw = rd.hget(KEY_META, name)
    if existing_raw:
        try:
            ex_meta = json.loads(existing_raw)
            created_at = ex_meta.get("created_at") or ex_meta.get("updated_at") or now_iso
        except Exception:
            pass

    meta = {
        "name": name,
        "type": gtype,
        "desc": desc,
        "ttl": effective_ttl,
        "created_at": created_at,
        "updated_at": now_iso
    }
    rd.hset(KEY_META, name, json.dumps(meta))


# 레거시 하위 호환 별칭
_save_group = save_redis_group


def calculate_and_refresh_dynamic_groups(db: Session, rd) -> Dict[str, int]:
    """
    [실 비즈니스 동적 타겟 그룹 자율 연산 엔진 (기존 10여 종 자동 그룹 100% 보장)]
    1. 오늘 휴무자 (today_dayoff): DayOff 승인된 인원
    2. 오늘 근무자 (today_working): 전체 활성 인원 - 오늘 휴무자
    3. 시내버스 운전자 (bus_city): primary/secondary 소속 '시내' 포함 인원
    4. 시외버스 운전자 (bus_intercity): primary/secondary 소속 '시외' 포함 인원
    5. 직급 랭크별 그룹 (rank_level_0 ~ 4, 9): 권한 등급별 사원 그룹 (과거 10여 종 그룹 원형 복원)
    6. 오늘 배차 노선별 기사 (dispatch_today_{route}): 당일 CONFIRMED 배차 노선별 기사
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
    save_redis_group(rd, "today_dayoff", today_dayoff_uids, "dynamic", "오늘 승인된 휴무/연차 대상자")
    refreshed_groups["today_dayoff"] = len(today_dayoff_uids)

    # 2. 오늘 실제 근무/운행 인원 (today_working = 전체 활성 사용자 - 오늘 휴무자)
    active_users = db.query(User.id).join(UserProfile, User.id == UserProfile.user_id).filter(
        UserProfile.is_active == True
    ).all()
    dayoff_set = set(today_dayoff_uids)
    today_working_uids = [str(u[0]) for u in active_users if str(u[0]) not in dayoff_set]
    save_redis_group(rd, "today_working", today_working_uids, "dynamic", "오늘 실제 근무/운행 중인 인원 (휴무자 제외)")
    refreshed_groups["today_working"] = len(today_working_uids)

    # 3. 소속 그룹 기반: 시내버스 / 시외버스 운전원
    all_profiles = db.query(User.id, UserProfile.primary_group, UserProfile.secondary_groups, UserProfile.rank_level).join(
        UserProfile, User.id == UserProfile.user_id
    ).filter(UserProfile.is_active == True).all()

    bus_city_uids = []
    bus_intercity_uids = []
    for uid, p_grp, s_grps, _ in all_profiles:
        p_str = p_grp or ""
        s_list = s_grps if isinstance(s_grps, list) else []
        all_grp_texts = [p_str] + [str(g) for g in s_list]
        if any("시내" in g for g in all_grp_texts):
            bus_city_uids.append(str(uid))
        if any("시외" in g for g in all_grp_texts):
            bus_intercity_uids.append(str(uid))

    save_redis_group(rd, "bus_city", bus_city_uids, "dynamic", "시내버스 전담 운전원")
    refreshed_groups["bus_city"] = len(bus_city_uids)

    save_redis_group(rd, "bus_intercity", bus_intercity_uids, "dynamic", "시외버스 전담 운전원")
    refreshed_groups["bus_intercity"] = len(bus_intercity_uids)

    # 4. 🏛️ 직급 랭크별 동적 그룹 (과거 10여 종 자동 그룹 원형 복원: rank_level_0 ~ 4, 9)
    rank_labels = {
        0: "게스트 / 대기 (Lv.0)",
        1: "일반 사원 (Lv.1)",
        2: "실무 / 주임 (Lv.2)",
        3: "중간관리자 / 과·차장 (Lv.3)",
        4: "부서장 / 임원 (Lv.4)",
        9: "최고 시스템 관리자 (Root Lv.9)"
    }
    for level, label in rank_labels.items():
        uids = [str(p[0]) for p in all_profiles if p[3] == level]
        grp_name = f"rank_level_{level}"
        save_redis_group(rd, grp_name, uids, "dynamic", f"직급 {label} 그룹")
        refreshed_groups[grp_name] = len(uids)

    # 5. 🏷️ 아이디 길이별 동적 그룹 (원형 100% 복원: 5자 이하, 6자 이상)
    all_users = db.query(User.id, User.username).all()
    short_ids = [str(u[0]) for u in all_users if len(u[1] or "") <= 5]
    long_ids = [str(u[0]) for u in all_users if len(u[1] or "") > 5]
    save_redis_group(rd, "id_length_short", short_ids, "dynamic", "아이디 5자 이하 대상자")
    refreshed_groups["id_length_short"] = len(short_ids)
    save_redis_group(rd, "id_length_long", long_ids, "dynamic", "아이디 6자 이상 대상자")
    refreshed_groups["id_length_long"] = len(long_ids)

    # 6. 오늘 배차 노선별 기사 그룹 (dispatch_today_{route_name})
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
        save_redis_group(rd, grp_name, list(uids), "dynamic", f"오늘 {route_name} 노선 배정 운행 기사")
        refreshed_groups[grp_name] = len(uids)

    logger.info(f"✨ 동적 타겟 그룹 연산 완료 ({len(refreshed_groups)}종): {refreshed_groups}")
    return refreshed_groups


def get_all_redis_groups(rd) -> List[Dict[str, Any]]:
    """현재 Redis에 등록된 모든 타겟 그룹 및 인원수, 생성/갱신 일시 조회 (인원이 0명이어도 정상 유지)"""
    metas = rd.hgetall(KEY_META)
    result = []
    for name, meta_str in metas.items():
        data_key = f"{KEY_DATA}{name}"
        meta = json.loads(meta_str)
        meta["count"] = rd.scard(data_key) if rd.exists(data_key) else 0
        ttl = rd.ttl(data_key)
        meta["ttl_seconds"] = ttl if ttl > 0 else meta.get("ttl", 0)
        if "created_at" not in meta:
            meta["created_at"] = meta.get("updated_at") or datetime.now().isoformat()
        result.append(meta)
    return result


def create_manual_redis_group(name: str, user_ids: List[int], rd) -> Dict[str, Any]:
    """수동 타겟 그룹 생성 (30일 안전 TTL 강제 적용)"""
    save_redis_group(
        rd=rd,
        name=name,
        uids=[str(uid) for uid in user_ids],
        gtype="manual",
        desc="관리자 수동 지정 그룹",
        ttl_seconds=DEFAULT_TTL_MANUAL
    )
    return {"message": "Success", "count": len(user_ids), "ttl_seconds": DEFAULT_TTL_MANUAL}


def combine_redis_groups(
    new_name: str,
    op: str,
    base_group: str,
    target_groups: List[str],
    rd
) -> Dict[str, Any]:
    """그룹간 집합 연산 (교집합 INTERSECT, 차집합 DIFF, 합집합 UNION) 및 30일 안전 TTL 강제 적용"""
    keys = [f"{KEY_DATA}{base_group}"] + [f"{KEY_DATA}{g}" for g in target_groups]
    dest_key = f"{KEY_DATA}{new_name}"

    if op == "INTERSECT":
        rd.sinterstore(dest_key, *keys)
    elif op == "DIFF":
        rd.sdiffstore(dest_key, *keys)
    elif op == "UNION":
        rd.sunionstore(dest_key, *keys)
    else:
        raise ValueError(f"지원하지 않는 집합 연산자입니다: {op}")

    # 안전 TTL (30일) 강제 적용 (STD-SYS-009)
    rd.expire(dest_key, DEFAULT_TTL_COMBINED)

    now_iso = datetime.now().isoformat()
    created_at = now_iso
    existing_raw = rd.hget(KEY_META, new_name)
    if existing_raw:
        try:
            ex_meta = json.loads(existing_raw)
            created_at = ex_meta.get("created_at") or ex_meta.get("updated_at") or now_iso
        except Exception:
            pass

    meta = {
        "name": new_name,
        "type": "combined",
        "desc": f"{op} 연산으로 생성된 그룹",
        "op": op,
        "parents": [base_group] + target_groups,
        "ttl": DEFAULT_TTL_COMBINED,
        "created_at": created_at,
        "updated_at": now_iso
    }
    rd.hset(KEY_META, new_name, json.dumps(meta))
    return {"name": new_name, "count": rd.scard(dest_key), "ttl_seconds": DEFAULT_TTL_COMBINED}


def delete_redis_group(name: str, rd) -> Dict[str, str]:
    """특정 Redis 타겟 그룹 삭제"""
    rd.delete(f"{KEY_DATA}{name}")
    rd.hdel(KEY_META, name)
    return {"message": "Success"}
