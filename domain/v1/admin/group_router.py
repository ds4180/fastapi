from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from redis_config import get_redis
from models import User, UserProfile, DayOff
import json

router = APIRouter(prefix="/v1/admin/groups", tags=["Admin Groups Management"])

# Redis Key Constants
KEY_DATA = "group:data:" # group:data:{name} -> Set of user_ids
KEY_META = "group:metadata" # group:metadata -> Hash {name: metadata_json}

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
    """다이나믹 그룹 강제 갱신 (직급별, 아이디 길이별 등)"""
    # 1. 직급별 그룹화
    profiles = db.query(UserProfile.user_id, UserProfile.rank_level).all()
    for level in range(5): # 0~4 랭크
        uids = [str(p.user_id) for p in profiles if p.rank_level == level]
        name = f"rank_level_{level}"
        _save_group(rd, name, uids, "dynamic", f"직급 레벨 {level} 그룹")

    # 2. 아이디 길이별 그룹화 (예: 5자 이하, 6자 이상)
    users = db.query(User.id, User.username).all()
    short_ids = [str(u.id) for u in users if len(u.username) <= 5]
    long_ids = [str(u.id) for u in users if len(u.username) > 5]
    
    _save_group(rd, "id_length_short", short_ids, "dynamic", "아이디 5자 이하")
    _save_group(rd, "id_length_long", long_ids, "dynamic", "아이디 6자 이상")

    return {"message": "Dynamic groups refreshed"}

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
