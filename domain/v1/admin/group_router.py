from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from database import get_db
from redis_config import get_redis
from core.deps import require_app_permission
from core.audit import safe_log_audit
from models.user import User, UserProfile
from domain.system.group_service import (
    calculate_and_refresh_dynamic_groups,
    get_all_redis_groups,
    create_manual_redis_group,
    combine_redis_groups,
    delete_redis_group,
    _save_group,
    KEY_DATA,
    KEY_META,
)

# 📌 외부 라우터/테스트 하위 호환성을 위해 Re-export 등록
__all__ = [
    "router",
    "calculate_and_refresh_dynamic_groups",
    "_save_group",
    "KEY_DATA",
    "KEY_META",
]

router = APIRouter(prefix="/v1/admin/groups", tags=["Admin Groups Management"])

# 🏛️ AppRegistry 거버넌스 연동 (target_groups)
check_target_groups_read = require_app_permission("target_groups", action="read")
check_target_groups_write = require_app_permission("target_groups", action="write")


@router.get("/candidates")
def get_group_candidates(
    db: Session = Depends(get_db),
    admin=Depends(check_target_groups_read)
):
    """
    [수동 타겟 그룹 생성용 사원 후보 목록 조회]
    - target_groups 거버넌스 랭킹/그룹 설정에 실시간 연동됩니다.
    - 주민번호/계좌 등 민감 정보를 배제하고 사원 선택에 필요한 최소 정보(id, username, real_name)만 안전하게 반환합니다.
    """
    users = db.query(User).all()
    result = []
    for u in users:
        is_active = True
        if hasattr(u, "profile") and u.profile:
            is_active = getattr(u.profile, "is_active", True)
        if is_active:
            result.append({
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name or u.username,
                "primary_group": u.profile.primary_group if (hasattr(u, "profile") and u.profile) else "소속없음"
            })
    return sorted(result, key=lambda x: x["real_name"])


@router.get("")
def get_all_groups(
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_read)
):
    """현재 생성된 모든 그룹(수동, 다이나믹, 복합) 목록 조회 (동적 그룹 기본 세트 누락 시 자동 1회 연산 복구)"""
    groups = get_all_redis_groups(rd)
    dynamic_count = sum(1 for g in groups if g.get("type") == "dynamic")
    # 기본 동적 그룹 10여 종이 누락되어 있으면 즉시 자가치유 재연산 실행
    if dynamic_count < 8:
        calculate_and_refresh_dynamic_groups(db, rd)
        groups = get_all_redis_groups(rd)
    return groups


@router.get("/{name}/members")
def get_group_members(
    name: str,
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_read)
):
    """
    [특정 타겟 그룹 소속 사원 명단 조회]
    Redis Set에서 user_id 목록을 조회한 후, DB의 User/UserProfile 정보를 매핑하여 반환합니다.
    """
    key = f"{KEY_DATA}{name}"
    uids_raw = rd.smembers(key)
    if not uids_raw:
        return []

    uids = []
    for ub in uids_raw:
        try:
            val = ub.decode("utf-8") if isinstance(ub, bytes) else str(ub)
            uids.append(int(val))
        except (ValueError, TypeError):
            pass

    if not uids:
        return []

    users = db.query(User).filter(User.id.in_(uids)).all()
    result = []
    for u in users:
        p = u.profile
        result.append({
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name or u.username,
            "primary_group": p.primary_group if p else "소속없음",
            "rank_level": p.rank_level if p else 0,
            "is_active": p.is_active if p else True
        })
    return sorted(result, key=lambda x: x["real_name"])


@router.post("/manual")
def create_manual_group(
    name: str = Body(...),
    user_ids: list[int] = Body(...),
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """수동 그룹 생성"""
    res = create_manual_redis_group(name=name, user_ids=user_ids, rd=rd)
    safe_log_audit(
        db=db,
        app_id="target_groups",
        log_type="CHANGE",
        action="CREATE_MANUAL_GROUP",
        title=f"수동 타겟 그룹 생성: '{name}'",
        user=admin,
        severity="INFO",
        resource_type="target_group",
        resource_id=name,
        message=f"관리자 '{admin.username}'이(가) 수동 타겟 그룹 '{name}'(인원: {len(user_ids)}명)을(를) 생성했습니다.",
        metadata={"group_name": name, "user_count": len(user_ids)}
    )
    return res


@router.post("/dynamic/refresh")
def refresh_dynamic_groups(
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """실 비즈니스 다이나믹 그룹 강제 연산 및 갱신"""
    results = calculate_and_refresh_dynamic_groups(db, rd)
    total_count = sum(results.values())
    safe_log_audit(
        db=db,
        app_id="target_groups",
        log_type="CHANGE",
        action="REFRESH_DYNAMIC_GROUPS",
        title="실시간 동적 타겟 그룹 재연산 갱신",
        user=admin,
        severity="INFO",
        resource_type="target_group",
        resource_id="dynamic_all",
        message=f"관리자 '{admin.username}'이(가) 동적 타겟 그룹 {len(results)}종(총 대상자: {total_count}명)을 실시간 재연산했습니다.",
        metadata={"refreshed_groups": results}
    )
    return {"message": "Dynamic groups refreshed", "results": results}


@router.post("/combine")
def combine_groups(
    new_name: str = Body(...),
    op: str = Body(..., description="INTERSECT | DIFF | UNION"),
    base_group: str = Body(...),
    target_groups: list[str] = Body(...),
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """그룹간 집합 연산 (교집합, 차집합, 합집합)"""
    try:
        res = combine_redis_groups(
            new_name=new_name,
            op=op,
            base_group=base_group,
            target_groups=target_groups,
            rd=rd
        )
        safe_log_audit(
            db=db,
            app_id="target_groups",
            log_type="CHANGE",
            action="COMBINE_GROUPS",
            title=f"복합 타겟 그룹 생성: '{new_name}' ({op})",
            user=admin,
            severity="INFO",
            resource_type="target_group",
            resource_id=new_name,
            message=f"관리자 '{admin.username}'이(가) 기준 그룹 '{base_group}'과 대상 {target_groups}에 대한 {op} 연산으로 새 그룹 '{new_name}'(인원: {res.get('count', 0)}명)을 생성했습니다.",
            metadata={"new_name": new_name, "op": op, "base_group": base_group, "target_groups": target_groups, "count": res.get("count", 0)}
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/{name}")
def delete_group(
    name: str,
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """특정 그룹 삭제 (데이터 및 메타데이터 제거)"""
    res = delete_redis_group(name=name, rd=rd)
    safe_log_audit(
        db=db,
        app_id="target_groups",
        log_type="CHANGE",
        action="DELETE_GROUP",
        title=f"타겟 그룹 삭제: '{name}'",
        user=admin,
        severity="WARN",
        resource_type="target_group",
        resource_id=name,
        message=f"관리자 '{admin.username}'이(가) 타겟 그룹 '{name}'을(를) 삭제했습니다.",
        metadata={"deleted_group": name}
    )
    return res
