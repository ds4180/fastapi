"""
============================================================================
[통합 조직·권한 그룹 관제 라우터 (domain/v1/admin/auth_group_router.py)]
============================================================================
- 모든 그룹 집계·Cascade 정화·사용자 배정·인스턴스 권한 비즈니스 로직은
  auth_group_admin_service 및 group_policy_service로 분리하고,
  본 라우터는 HTTP 입출력, AppRegistry('group_manage') 4단계 권한 인가 및 감사로그만 담당합니다.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import require_app_permission
from core.permission import ROOT_RANK, can_access_app, get_user_rank
from database import get_db
from domain.system.auth_group_admin_service import (
    add_user_secondary_group_item,
    create_group_master_item,
    delete_group_master_item,
    extract_all_groups_from_spec,
    list_all_instance_permissions,
    list_app_permissions,
    list_group_masters,
    list_user_groups,
    remove_group_from_spec,
    remove_user_secondary_group_item,
    set_user_groups_batch,
    set_user_primary_group,
    update_app_permission_item,
    update_group_master_item,
    update_instance_permission_item,
)
from domain.system.group_policy_service import (
    get_group_manage_settings,
    update_group_manage_settings,
)
from domain.v1.admin.auth_group_schema import (
    AppPermissionItemRes,
    AppPermissionsUpdateReq,
    GroupCreateReq,
    GroupItemRes,
    GroupUpdateReq,
    InstancePermissionItemRes,
    InstancePermissionUpdateReq,
    UserGroupBatchReq,
    UserGroupItemRes,
    UserPrimaryGroupReq,
    UserSecondaryGroupReq,
)
from models import AppRegistry, User

router = APIRouter(prefix="/v1/admin/auth-groups", tags=["Admin Auth Groups"])

check_groups_read = require_app_permission("group_manage", action="read")
check_groups_write = require_app_permission("group_manage", action="write")


def _can_write_groups(user: User, db: Session) -> bool:
    if get_user_rank(user) == ROOT_RANK:
        return True
    app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "group_manage").first()
    if not app_meta:
        return get_user_rank(user) >= 8
    return can_access_app(user, app_meta, action="write")


def _maybe_log_group_audit(
    db: Session,
    user: User,
    *,
    action: str,
    title: str,
    resource_type: str,
    resource_id: Any,
    message: str,
    severity: str = "INFO",
    log_type: str = "SECURITY",
    metadata: Optional[Dict[str, Any]] = None,
    diff_payload: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not get_group_manage_settings(db).get("audit_group_changes", True):
        return
    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type=log_type,
        action=action,
        title=title,
        user=user,
        severity=severity,
        resource_type=resource_type,
        resource_id=str(resource_id),
        message=message,
        metadata={**(metadata or {}), "admin_id": user.id},
        diff_payload=diff_payload,
    )


# ==========================================================================
# ⚙️ 0. 그룹·권한 관리 정책 설정 API
# ==========================================================================


@router.get("/settings", summary="그룹·권한 관리 통합 정책 설정 조회")
def get_group_manage_settings_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read),
):
    return {
        "settings": get_group_manage_settings(db),
        "permissions": {
            "can_write": _can_write_groups(current_user, db),
        },
    }


@router.put("/settings", summary="그룹·권한 관리 통합 정책 설정 저장")
def update_group_manage_settings_api(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    old_cfg, new_cfg = update_group_manage_settings(db, payload)
    diff_payload = [
        {"field": k, "from": old_cfg.get(k), "to": new_cfg.get(k)}
        for k in new_cfg
        if old_cfg.get(k) != new_cfg.get(k)
    ]
    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type="CHANGE",
        severity="INFO",
        action="GROUP_SETTINGS_UPDATED",
        title=f"관리자({current_user.username})에 의한 그룹·권한 정책 설정 변경",
        user=current_user,
        resource_type="system_config",
        resource_id="group_manage_settings",
        diff_payload=diff_payload,
        message=f"그룹·권한 관리 정책 {len(diff_payload)}개 항목을 갱신했습니다.",
    )
    return {
        "message": "그룹·권한 관리 정책 설정이 저장되었습니다.",
        "settings": new_cfg,
    }


# ==========================================================================
# 📂 1. 그룹 뷰 (Group View) API
# ==========================================================================


@router.get("/master", response_model=List[GroupItemRes], summary="공식 그룹 마스터 전체 목록 조회")
def get_group_master_list(
    group_type: Optional[str] = Query(None, description="PRIMARY | SECONDARY 필터"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read),
):
    return list_group_masters(db, group_type=group_type)


@router.post("/master", response_model=GroupItemRes, status_code=status.HTTP_201_CREATED, summary="신규 공식 그룹 생성")
def create_group_master(
    req: GroupCreateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    new_group, res = create_group_master_item(db, req)
    _maybe_log_group_audit(
        db,
        current_user,
        action="GROUP_CREATED",
        title=f"신규 권한 그룹 생성: [{new_group.name}] ({new_group.code})",
        resource_type="group",
        resource_id=new_group.id,
        message=f"관리자 '{current_user.username}'이(가) 신규 {new_group.group_type} 그룹 [{new_group.name}](코드: {new_group.code})을(를) 생성했습니다.",
        metadata={"group_id": new_group.id, "code": new_group.code, "name": new_group.name, "group_type": new_group.group_type},
    )
    return res


@router.put("/master/{group_id}", response_model=GroupItemRes, summary="공식 그룹 정보 수정")
def update_group_master(
    group_id: int,
    req: GroupUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    group, res = update_group_master_item(db, group_id, req)
    _maybe_log_group_audit(
        db,
        current_user,
        action="GROUP_UPDATED",
        title=f"권한 그룹 정보 수정: [{group.name}] ({group.code})",
        resource_type="group",
        resource_id=group.id,
        message=f"관리자 '{current_user.username}'이(가) 그룹 [{group.name}]의 메타 정보를 수정했습니다.",
        metadata={"group_id": group.id, "code": group.code, "name": group.name},
    )
    return res


@router.delete("/master/{group_id}", summary="공식 그룹 삭제 (정책 검증 및 Cascade 자동 정화)")
def delete_group_master(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    deleted_code, deleted_name, refs = delete_group_master_item(db, group_id)
    _maybe_log_group_audit(
        db,
        current_user,
        action="GROUP_DELETED",
        title=f"권한 그룹 삭제 및 연계 해제: [{deleted_name}] ({deleted_code})",
        severity="WARN",
        resource_type="group",
        resource_id=group_id,
        message=f"관리자 '{current_user.username}'이(가) 그룹 [{deleted_name}](코드: {deleted_code})을(를) 영구 삭제하고 연계된 회원({refs['member_refs']}명) 및 리소스({refs['resource_refs']}곳)를 정화했습니다.",
        metadata={"deleted_group_id": group_id, "deleted_code": deleted_code, **refs},
    )
    return {"message": "Success", "deleted_code": deleted_code}


# ==========================================================================
# 👤 2. 사용자 뷰 (User View) API
# ==========================================================================


@router.get("/users", response_model=List[UserGroupItemRes], summary="사용자별 그룹 매칭 현황 목록 조회")
def get_user_group_list(
    query: Optional[str] = Query(None, description="이름/아이디/이메일 검색"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read),
):
    return list_user_groups(db, query=query)


@router.patch("/users/{user_id}/primary", summary="사용자 주그룹 단일 설정/해제")
def update_user_primary_group(
    user_id: int,
    req: UserPrimaryGroupReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    updated_primary = set_user_primary_group(db, user_id, req.primary_group)
    _maybe_log_group_audit(
        db,
        current_user,
        action="USER_PRIMARY_GROUP_CHANGED",
        title=f"사용자 #{user_id} 주그룹 변경: {updated_primary or '소속없음'}",
        resource_type="user",
        resource_id=user_id,
        message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}의 주그룹을 '{updated_primary or '소속없음'}'(으)로 변경했습니다.",
        metadata={"target_user_id": user_id, "primary_group": updated_primary},
    )
    return {"message": "Success", "user_id": user_id, "primary_group": updated_primary}


@router.post("/users/{user_id}/secondary", summary="사용자 부그룹 추가")
def add_user_secondary_group(
    user_id: int,
    req: UserSecondaryGroupReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    updated_list, added = add_user_secondary_group_item(db, user_id, req.code)
    if added:
        _maybe_log_group_audit(
            db,
            current_user,
            action="USER_SECONDARY_GROUP_ADDED",
            title=f"사용자 #{user_id} 부그룹 추가: [{req.code}]",
            resource_type="user",
            resource_id=user_id,
            message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}에게 부그룹 [{req.code}]을(를) 부여했습니다.",
            metadata={"target_user_id": user_id, "added_group": req.code},
        )
    return {"message": "Success", "user_id": user_id, "secondary_groups": updated_list}


@router.delete("/users/{user_id}/secondary/{code}", summary="사용자 부그룹 해제")
def remove_user_secondary_group(
    user_id: int,
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    updated_list, removed = remove_user_secondary_group_item(db, user_id, code)
    if removed:
        _maybe_log_group_audit(
            db,
            current_user,
            action="USER_SECONDARY_GROUP_REMOVED",
            title=f"사용자 #{user_id} 부그룹 해제: [{code}]",
            resource_type="user",
            resource_id=user_id,
            message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}에게서 부그룹 [{code}]을(를) 해제했습니다.",
            metadata={"target_user_id": user_id, "removed_group": code},
        )
    return {"message": "Success", "user_id": user_id, "secondary_groups": updated_list}


@router.put("/users/{user_id}/groups", summary="사용자 주그룹 및 부그룹 일괄 설정")
def update_user_groups_batch(
    user_id: int,
    req: UserGroupBatchReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    new_primary, new_secondary = set_user_groups_batch(db, user_id, req)
    _maybe_log_group_audit(
        db,
        current_user,
        action="USER_GROUPS_BATCH_UPDATED",
        title=f"사용자 #{user_id} 주/부그룹 일괄 설정",
        resource_type="user",
        resource_id=user_id,
        message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}의 그룹을 일괄 수정했습니다. (주: {new_primary or '없음'}, 부: {len(new_secondary)}개)",
        metadata={"target_user_id": user_id, "primary_group": new_primary, "secondary_groups": new_secondary},
    )
    return {
        "message": "Success",
        "user_id": user_id,
        "primary_group": new_primary,
        "secondary_groups": new_secondary,
    }


# ==========================================================================
# 📱 3. 앱 & 통합 인스턴스 뷰 (App / Instance View) API
# ==========================================================================


@router.get("/apps", response_model=List[AppPermissionItemRes], summary="등록된 앱 전체 권한 설정 현황 조회")
def get_app_permission_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read),
):
    return list_app_permissions(db)


@router.patch("/apps/{app_id}/permissions", response_model=AppPermissionItemRes, summary="앱 권한 랭킹 및 allow/deny 설정 변경")
def update_app_permissions(
    app_id: str,
    req: AppPermissionsUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    app, res = update_app_permission_item(db, app_id, req)
    _maybe_log_group_audit(
        db,
        current_user,
        action="APP_PERMISSION_CHANGED",
        title=f"앱 권한 변경: [{app.name}] ({app.app_id}, R:{app.min_read_rank}/W:{app.min_write_rank})",
        resource_type="app_registry",
        resource_id=app.app_id,
        message=f"관리자 '{current_user.username}'이(가) 앱 [{app.name}]의 권한(R:{app.min_read_rank}, W:{app.min_write_rank})을 수정했습니다.",
        metadata={"app_id": app.app_id, "min_read_rank": app.min_read_rank, "min_write_rank": app.min_write_rank},
    )
    return res


@router.get("/instances", response_model=List[InstancePermissionItemRes], summary="전체 인스턴스 권한 설정 현황 목록 조회")
def get_all_instance_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read),
):
    return list_all_instance_permissions(db)


@router.patch("/instances/{instance_type}/{target_id}/permissions", response_model=InstancePermissionItemRes, summary="인스턴스 권한 랭킹 및 allow/deny 설정 변경")
def update_instance_permissions(
    instance_type: str,
    target_id: str,
    req: InstancePermissionUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write),
):
    res, audit_meta = update_instance_permission_item(db, instance_type, target_id, req)
    _maybe_log_group_audit(
        db,
        current_user,
        action="INSTANCE_PERMISSION_CHANGED",
        title=audit_meta["title"],
        resource_type=audit_meta["resource_type"],
        resource_id=audit_meta["resource_id"],
        message=f"관리자 '{current_user.username}'이(가) {audit_meta['title']} 작업을 수행했습니다.",
        metadata=audit_meta["meta"],
    )
    return res


# 하위 호환 re-export
__all__ = ["router", "remove_group_from_spec", "extract_all_groups_from_spec"]
