from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from database import get_db
from redis_config import get_redis
from core.deps import require_app_permission
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

# 🏛️ AppRegistry 거버넌스 연동 (admin_target_groups)
check_target_groups_read = require_app_permission("admin_target_groups", action="read")
check_target_groups_write = require_app_permission("admin_target_groups", action="write")


@router.get("")
def get_all_groups(
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_read)
):
    """현재 생성된 모든 그룹(수동, 다이나믹, 복합) 목록 조회"""
    return get_all_redis_groups(rd)


@router.post("/manual")
def create_manual_group(
    name: str = Body(...),
    user_ids: list[int] = Body(...),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """수동 그룹 생성"""
    return create_manual_redis_group(name=name, user_ids=user_ids, rd=rd)


@router.post("/dynamic/refresh")
def refresh_dynamic_groups(
    db: Session = Depends(get_db),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """실 비즈니스 다이나믹 그룹 강제 연산 및 갱신"""
    results = calculate_and_refresh_dynamic_groups(db, rd)
    return {"message": "Dynamic groups refreshed", "results": results}


@router.post("/combine")
def combine_groups(
    new_name: str = Body(...),
    op: str = Body(..., description="INTERSECT | DIFF | UNION"),
    base_group: str = Body(...),
    target_groups: list[str] = Body(...),
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """그룹간 집합 연산 (교집합, 차집합, 합집합)"""
    try:
        return combine_redis_groups(
            new_name=new_name,
            op=op,
            base_group=base_group,
            target_groups=target_groups,
            rd=rd
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/{name}")
def delete_group(
    name: str,
    rd=Depends(get_redis),
    admin=Depends(check_target_groups_write)
):
    """특정 그룹 삭제 (데이터 및 메타데이터 제거)"""
    return delete_redis_group(name=name, rd=rd)
