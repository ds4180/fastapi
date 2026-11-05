"""
============================================================================
[통합 조직·권한 그룹 관제 라우터 (domain/v1/admin/auth_group_router.py)]
============================================================================

3대 뷰 (그룹 뷰 / 사용자 뷰 / 앱 뷰) 전용 API 엔드포인트를 제공합니다.
- 그룹 생성·삭제 및 앱 권한(allow/deny/랭킹) 제어는 오직 root(rank_level == 9)만 허용합니다.
- 그룹 삭제 시 사용자 프로필 및 앱 레지스트리에서 연계된 코드를 자동 Cascade 정화합니다.
"""

from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import User, UserProfile, Group, AppRegistry, BoardConfig, Page
from core.deps import get_current_user, require_app_permission
from core.audit import safe_log_audit
from domain.v1.admin.auth_group_schema import (
    GroupCreateReq,
    GroupUpdateReq,
    GroupItemRes,
    UserGroupItemRes,
    UserPrimaryGroupReq,
    UserSecondaryGroupReq,
    UserGroupBatchReq,
    AppPermissionItemRes,
    AppPermissionsUpdateReq,
    InstancePermissionItemRes,
    InstancePermissionUpdateReq,
)

router = APIRouter(prefix="/v1/admin/auth-groups", tags=["Admin Auth Groups"])

# 🏛️ AppRegistry 거버넌스 연동 (group_manage)
check_groups_read = require_app_permission("group_manage", action="read")
check_groups_write = require_app_permission("group_manage", action="write")


def remove_group_from_spec(spec: Any, target_code: str) -> tuple[Any, bool]:
    """
    allow_groups 또는 deny_groups (단순 리스트 or JSONB 딕셔너리)에서 target_code를 안전하게 제거합니다.
    """
    if not spec:
        return spec, False
    if isinstance(spec, list):
        if target_code in spec:
            return [g for g in spec if g != target_code], True
        return spec, False
    if isinstance(spec, dict):
        changed = False
        new_dict = {}
        for action, groups in spec.items():
            if isinstance(groups, list):
                if target_code in groups:
                    new_dict[action] = [g for g in groups if g != target_code]
                    changed = True
                else:
                    new_dict[action] = groups
            else:
                new_dict[action] = groups
        return (new_dict, True) if changed else (spec, False)
    return spec, False


def extract_all_groups_from_spec(spec: Any) -> set[str]:
    """
    [JSONB 듀얼 모드 안전 그룹 추출기]
    allow_groups 또는 deny_groups (단순 리스트 or JSONB 딕셔너리)에서 실제 그룹 코드 목록만 안전하게 추출합니다.
    - 리스트 모드: ["운수팀", "배차담당"] -> {"운수팀", "배차담당"}
    - 딕셔너리 모드: {"read": ["운수팀"], "write": ["배차담당"], "all": ["기획실"]} -> {"운수팀", "배차담당", "기획실"}
    - 🌟 파이썬 dict 순회 시 'read', 'write' 키가 그룹 코드로 둔갑하는 버그를 원천 차단합니다.
    """
    if not spec:
        return set()
    if isinstance(spec, (list, set, tuple)):
        return {str(g) for g in spec if g}
    if isinstance(spec, dict):
        result = set()
        for val in spec.values():
            if isinstance(val, (list, set, tuple)):
                for g in val:
                    if g:
                        result.add(str(g))
            elif isinstance(val, str) and val:
                result.add(val)
        return result
    if isinstance(spec, str) and spec:
        return {spec}
    return set()


# ==========================================================================
# 📂 1. 그룹 뷰 (Group View) API
# ==========================================================================

@router.get("/master", response_model=List[GroupItemRes], summary="공식 그룹 마스터 전체 목록 조회")
def get_group_master_list(
    group_type: Optional[str] = Query(None, description="PRIMARY | SECONDARY 필터"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read)
):
    """
    등록된 모든 주그룹 및 부그룹 목록을 반환합니다.
    각 그룹별로 현재 매칭된 회원 수(주/부) 및 allow/deny로 적용 중인 앱 이름을 함께 집계합니다.
    """
    query = db.query(Group)
    if group_type:
        query = query.filter(Group.group_type == group_type)
    groups = query.order_by(Group.group_type, Group.id).all()

    # 회원 프로필 전체 조회 (메모리 집계)
    profiles = db.query(UserProfile.primary_group, UserProfile.secondary_groups).all()
    primary_counts = {}
    secondary_counts = {}
    for p in profiles:
        if p.primary_group:
            primary_counts[p.primary_group] = primary_counts.get(p.primary_group, 0) + 1
        if p.secondary_groups and isinstance(p.secondary_groups, list):
            for sec in p.secondary_groups:
                secondary_counts[sec] = secondary_counts.get(sec, 0) + 1

    # 앱 레지스트리 전체 조회 (메모리 집계 - JSONB 듀얼 규격 안전 처리)
    apps = db.query(AppRegistry.name, AppRegistry.allow_groups, AppRegistry.deny_groups).all()
    allow_map = {}
    deny_map = {}
    for a in apps:
        for g in extract_all_groups_from_spec(a.allow_groups):
            allow_map.setdefault(g, []).append(a.name)
        for g in extract_all_groups_from_spec(a.deny_groups):
            deny_map.setdefault(g, []).append(a.name)

    result = []
    for g in groups:
        result.append(GroupItemRes(
            id=g.id,
            code=g.code,
            name=g.name,
            group_type=g.group_type,
            category=g.category,
            description=g.description,
            created_at=g.created_at,
            primary_count=primary_counts.get(g.code, 0),
            secondary_count=secondary_counts.get(g.code, 0),
            allow_apps=allow_map.get(g.code, []),
            deny_apps=deny_map.get(g.code, []),
        ))
    return result


@router.post("/master", response_model=GroupItemRes, status_code=status.HTTP_201_CREATED, summary="신규 공식 그룹 생성")
def create_group_master(
    req: GroupCreateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    새로운 주그룹 또는 부그룹을 등록합니다. (오직 root만 수행 가능)
    """
    # 코드 중복 검사
    existing = db.query(Group).filter(Group.code == req.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"이미 등록된 그룹 식별 코드입니다: '{req.code}'"
        )

    new_group = Group(
        code=req.code.strip(),
        name=req.name.strip(),
        group_type=req.group_type,
        category=req.category,
        description=req.description.strip() if req.description else None,
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type="SECURITY",
        action="GROUP_CREATED",
        title=f"신규 권한 그룹 생성: [{new_group.name}] ({new_group.code})",
        user=current_user,
        severity="INFO",
        resource_type="group",
        resource_id=new_group.id,
        message=f"관리자 '{current_user.username}'이(가) 신규 {new_group.group_type} 그룹 [{new_group.name}](코드: {new_group.code})을(를) 생성했습니다.",
        metadata={"group_id": new_group.id, "code": new_group.code, "name": new_group.name, "group_type": new_group.group_type}
    )

    return GroupItemRes(
        id=new_group.id,
        code=new_group.code,
        name=new_group.name,
        group_type=new_group.group_type,
        category=new_group.category,
        description=new_group.description,
        created_at=new_group.created_at,
        primary_count=0,
        secondary_count=0,
        allow_apps=[],
        deny_apps=[],
    )


@router.put("/master/{group_id}", response_model=GroupItemRes, summary="공식 그룹 정보 수정")
def update_group_master(
    group_id: int,
    req: GroupUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    그룹 표시명, 카테고리, 설명을 수정합니다.
    식별 코드(code)는 데이터 무결성을 위해 변경 불가합니다.
    """
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="그룹을 찾을 수 없습니다.")

    if req.name is not None:
        group.name = req.name.strip()
    if req.category is not None:
        group.category = req.category
    if req.description is not None:
        group.description = req.description.strip()

    db.commit()
    db.refresh(group)

    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type="SECURITY",
        action="GROUP_UPDATED",
        title=f"권한 그룹 정보 수정: [{group.name}] ({group.code})",
        user=current_user,
        severity="INFO",
        resource_type="group",
        resource_id=group.id,
        message=f"관리자 '{current_user.username}'이(가) 그룹 [{group.name}]의 메타 정보를 수정했습니다.",
        metadata={"group_id": group.id, "code": group.code, "name": group.name}
    )

    # 회원 및 앱 카운트 집계
    p_count = db.query(UserProfile).filter(UserProfile.primary_group == group.code).count()
    return GroupItemRes(
        id=group.id,
        code=group.code,
        name=group.name,
        group_type=group.group_type,
        category=group.category,
        description=group.description,
        created_at=group.created_at,
        primary_count=p_count,
        secondary_count=0,
        allow_apps=[],
        deny_apps=[],
    )


@router.delete("/master/{group_id}", summary="공식 그룹 삭제 (Cascade 자동 정화)")
def delete_group_master(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    그룹을 삭제하고, 해당 그룹을 주그룹/부그룹으로 쓰던 회원 프로필과 앱 allow/deny 목록에서 자동 정리합니다.
    (오직 root만 수행 가능)
    """
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="삭제할 그룹을 찾을 수 없습니다.")

    deleted_code = group.code

    # 1. 주그룹 해제: primary_group == deleted_code ➔ None
    db.query(UserProfile).filter(UserProfile.primary_group == deleted_code).update(
        {"primary_group": None}, synchronize_session="fetch"
    )

    # 2. 부그룹 제거: secondary_groups 에서 deleted_code 제거
    affected_profiles = db.query(UserProfile).filter(
        UserProfile.secondary_groups.contains([deleted_code])
    ).all()
    for prof in affected_profiles:
        if isinstance(prof.secondary_groups, list) and deleted_code in prof.secondary_groups:
            prof.secondary_groups = [g for g in prof.secondary_groups if g != deleted_code]

    # 3. 앱, 게시판, 페이지 allow/deny 목록에서 deleted_code 안전 정화 (JSONB 듀얼 모드 완벽 지원)
    for app in db.query(AppRegistry).all():
        allow_cleaned, c1 = remove_group_from_spec(app.allow_groups, deleted_code)
        deny_cleaned, c2 = remove_group_from_spec(app.deny_groups, deleted_code)
        if c1:
            app.allow_groups = allow_cleaned
        if c2:
            app.deny_groups = deny_cleaned
        if c1 or c2:
            db.add(app)

    for board in db.query(BoardConfig).all():
        allow_cleaned, c1 = remove_group_from_spec(board.allow_groups, deleted_code)
        deny_cleaned, c2 = remove_group_from_spec(board.deny_groups, deleted_code)
        if c1:
            board.allow_groups = allow_cleaned
        if c2:
            board.deny_groups = deny_cleaned
        if c1 or c2:
            db.add(board)

    for page_obj in db.query(Page).all():
        allow_cleaned, c1 = remove_group_from_spec(page_obj.allow_groups, deleted_code)
        deny_cleaned, c2 = remove_group_from_spec(page_obj.deny_groups, deleted_code)
        if c1:
            page_obj.allow_groups = allow_cleaned
        if c2:
            page_obj.deny_groups = deny_cleaned
        if c1 or c2:
            db.add(page_obj)

    # 4. 그룹 레코드 삭제
    db.delete(group)
    db.commit()

    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type="SECURITY",
        action="GROUP_DELETED",
        title=f"권한 그룹 삭제 및 연계 해제: [{group.name}] ({deleted_code})",
        user=current_user,
        severity="WARNING",
        resource_type="group",
        resource_id=group_id,
        message=f"관리자 '{current_user.username}'이(가) 그룹 [{group.name}](코드: {deleted_code})을(를) 영구 삭제하고 연계된 회원 및 인스턴스 설정을 자동 정화했습니다.",
        metadata={"deleted_group_id": group_id, "deleted_code": deleted_code}
    )

    return {"message": "Success", "deleted_code": deleted_code}


# ==========================================================================
# 👤 2. 사용자 뷰 (User View) API
# ==========================================================================

@router.get("/users", response_model=List[UserGroupItemRes], summary="사용자별 그룹 매칭 현황 목록 조회")
def get_user_group_list(
    query: Optional[str] = Query(None, description="이름/아이디/이메일 검색"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read)
):
    """
    모든 회원의 기본 정보, 권한 등급, 주그룹(1개), 부그룹(N개) 현황을 조회합니다.
    """
    q = db.query(User).join(User.profile)
    if query:
        search = f"%{query}%"
        q = q.filter(
            (User.username.ilike(search)) |
            (User.real_name.ilike(search)) |
            (User.email.ilike(search))
        )
    users = q.order_by(User.id).all()

    result = []
    for u in users:
        result.append(UserGroupItemRes(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            email=u.email,
            rank_level=u.rank(),
            primary_group=u.primary_group,
            secondary_groups=u.secondary_groups,
        ))
    return result


@router.patch("/users/{user_id}/primary", summary="사용자 주그룹 단일 설정/해제")
def update_user_primary_group(
    user_id: int,
    req: UserPrimaryGroupReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    특정 회원의 주그룹(1순위 본소속)을 설정하거나 해제합니다.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    if req.primary_group:
        # 그룹 테이블에 존재하는지 확인
        g = db.query(Group).filter(Group.code == req.primary_group).first()
        if not g:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"존재하지 않는 그룹 코드입니다: '{req.primary_group}'")
        profile.primary_group = g.code
    else:
        profile.primary_group = None

    db.commit()

    safe_log_audit(
        db=db,
        app_id="group_manage",
        log_type="SECURITY",
        action="USER_PRIMARY_GROUP_CHANGED",
        title=f"사용자 #{user_id} 주그룹 변경: {profile.primary_group or '소속없음'}",
        user=current_user,
        severity="INFO",
        resource_type="user",
        resource_id=user_id,
        message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}의 주그룹을 '{profile.primary_group or '소속없음'}'(으)로 변경했습니다.",
        metadata={"target_user_id": user_id, "primary_group": profile.primary_group}
    )

    return {"message": "Success", "user_id": user_id, "primary_group": profile.primary_group}


@router.post("/users/{user_id}/secondary", summary="사용자 부그룹 추가")
def add_user_secondary_group(
    user_id: int,
    req: UserSecondaryGroupReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    특정 회원에게 부그룹(직무/특권/제재)을 추가합니다.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    g = db.query(Group).filter(Group.code == req.code).first()
    if not g:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"존재하지 않는 그룹 코드입니다: '{req.code}'")

    current_sec = list(profile.secondary_groups or [])
    if req.code not in current_sec:
        current_sec.append(req.code)
        profile.secondary_groups = current_sec
        db.commit()

        safe_log_audit(
            db=db,
            app_id="group_manage",
            log_type="SECURITY",
            action="USER_SECONDARY_GROUP_ADDED",
            title=f"사용자 #{user_id} 부그룹 추가: [{req.code}]",
            user=current_user,
            severity="INFO",
            resource_type="user",
            resource_id=user_id,
            message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}에게 부그룹 [{req.code}]을(를) 부여했습니다.",
            metadata={"target_user_id": user_id, "added_group": req.code}
        )

    return {"message": "Success", "user_id": user_id, "secondary_groups": profile.secondary_groups}


@router.delete("/users/{user_id}/secondary/{code}", summary="사용자 부그룹 해제")
def remove_user_secondary_group(
    user_id: int,
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    특정 회원의 부그룹 목록에서 특정 그룹을 제거합니다.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    current_sec = list(profile.secondary_groups or [])
    if code in current_sec:
        profile.secondary_groups = [g for g in current_sec if g != code]
        db.commit()

        safe_log_audit(
            db=db,
            app_id="group_manage",
            log_type="SECURITY",
            action="USER_SECONDARY_GROUP_REMOVED",
            title=f"사용자 #{user_id} 부그룹 해제: [{code}]",
            user=current_user,
            severity="INFO",
            resource_type="user",
            resource_id=user_id,
            message=f"관리자 '{current_user.username}'이(가) 회원 #{user_id}에게서 부그룹 [{code}]을(를) 해제했습니다.",
            metadata={"target_user_id": user_id, "removed_group": code}
        )

    return {"message": "Success", "user_id": user_id, "secondary_groups": profile.secondary_groups}


@router.put("/users/{user_id}/groups", summary="사용자 주그룹 및 부그룹 일괄 설정")
def update_user_groups_batch(
    user_id: int,
    req: UserGroupBatchReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    사용자의 주그룹과 부그룹을 일괄 변경합니다.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    profile.primary_group = req.primary_group or None
    profile.secondary_groups = req.secondary_groups or []
    db.commit()
    return {"message": "Success", "user_id": user_id, "primary_group": profile.primary_group, "secondary_groups": profile.secondary_groups}


# ==========================================================================
# 📱 3. 앱 뷰 (App View) API
# ==========================================================================

@router.get("/apps", response_model=List[AppPermissionItemRes], summary="등록된 앱 전체 권한 설정 현황 조회")
def get_app_permission_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read)
):
    """
    등록된 모든 앱의 읽기/쓰기 최소 랭킹(0~9) 및 allow/deny 그룹 목록을 조회합니다.
    """
    apps = db.query(AppRegistry).order_by(AppRegistry.app_id).all()
    result = []
    for a in apps:
        result.append(AppPermissionItemRes(
            app_id=a.app_id,
            name=a.name,
            title=a.title,
            description=a.description,
            app_type=a.app_type,
            min_read_rank=a.min_read_rank,
            min_write_rank=a.min_write_rank,
            allow_groups=a.allow_groups or [],
            deny_groups=a.deny_groups or [],
        ))
    return result


@router.patch("/apps/{app_id}/permissions", response_model=AppPermissionItemRes, summary="앱 권한 랭킹 및 allow/deny 설정 변경")
def update_app_permissions(
    app_id: str,
    req: AppPermissionsUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    특정 앱의 읽기/쓰기 최소 랭킹(0~9) 및 allow/deny 그룹을 수정합니다. (오직 root만 수행 가능)
    """
    app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="앱을 찾을 수 없습니다.")

    if req.min_read_rank is not None:
        app.min_read_rank = req.min_read_rank
    if req.min_write_rank is not None:
        app.min_write_rank = req.min_write_rank
    if req.allow_groups is not None:
        app.allow_groups = req.allow_groups
    if req.deny_groups is not None:
        app.deny_groups = req.deny_groups

    db.commit()
    db.refresh(app)

    return AppPermissionItemRes(
        app_id=app.app_id,
        name=app.name,
        title=app.title,
        description=app.description,
        app_type=app.app_type,
        min_read_rank=app.min_read_rank,
        min_write_rank=app.min_write_rank,
        allow_groups=app.allow_groups or [],
        deny_groups=app.deny_groups or [],
    )


# ==========================================================================
# 🧩 4. 통합 인스턴스 뷰 (Instance View) API (게시판/페이지/커스텀앱 인스턴스)
# ==========================================================================

@router.get("/instances", response_model=List[InstancePermissionItemRes], summary="전체 인스턴스 권한 설정 현황 목록 조회")
def get_all_instance_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_read)
):
    """
    모든 게시판 인스턴스(BoardConfig), 페이지 인스턴스(Page), 커스텀 단일 앱(AppRegistry)을
    통합 인스턴스 목록으로 추출하여 반환합니다.
    """
    result = []

    # 1. 📋 게시판 인스턴스 목록
    boards = db.query(BoardConfig).order_by(BoardConfig.id).all()
    for b in boards:
        result.append(InstancePermissionItemRes(
            target_id=str(b.id),
            instance_type="BOARD",
            app_type="INSTANCE",
            title=f"{b.name} 게시판",
            slug=b.slug,
            parent_engine="게시판 (board)",
            icon="mdi:clipboard-text-outline",
            min_read_rank=b.min_read_rank,
            min_write_rank=b.min_write_rank,
            allow_groups=b.allow_groups or [],
            deny_groups=b.deny_groups or [],
        ))

    # 2. 📄 페이지 인스턴스 목록
    pages = db.query(Page).filter(Page.is_deleted == False).order_by(Page.id).all()
    for p in pages:
        result.append(InstancePermissionItemRes(
            target_id=str(p.id),
            instance_type="PAGE",
            app_type="CUSTOM",
            title=f"{p.title} 페이지",
            slug=p.slug,
            parent_engine="페이지 (page)",
            icon="mdi:file-document-edit-outline",
            min_read_rank=p.min_rank if p.min_rank is not None else 0,
            min_write_rank=9, # 페이지 수정은 관리자/root 수준
            allow_groups=p.allow_groups or [],
            deny_groups=p.deny_groups or [],
        ))

    # 3. 📱 단일 비즈니스 앱 목록 (CUSTOM / SYSTEM 등 인스턴스가 1개인 독립 앱들)
    apps = db.query(AppRegistry).filter(AppRegistry.app_type != "INSTANCE").order_by(AppRegistry.app_id).all()
    for a in apps:
        result.append(InstancePermissionItemRes(
            target_id=a.app_id,
            instance_type="APP",
            app_type=a.app_type or "SYSTEM",
            title=a.name,
            slug=a.app_id,
            frontend_route=a.frontend_route,
            parent_engine=f"단일 앱 ({a.app_type})",
            icon=a.icon_default or "mdi:apps",
            min_read_rank=a.min_read_rank,
            min_write_rank=a.min_write_rank,
            allow_groups=a.allow_groups or [],
            deny_groups=a.deny_groups or [],
        ))

    return result


@router.patch("/instances/{instance_type}/{target_id}/permissions", response_model=InstancePermissionItemRes, summary="인스턴스 권한 랭킹 및 allow/deny 설정 변경")
def update_instance_permissions(
    instance_type: str,
    target_id: str,
    req: InstancePermissionUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_groups_write)
):
    """
    특정 인스턴스(게시판, 페이지, 커스텀앱)의 4단계 권한(랭킹, allow, deny)을 수정합니다. (root 전용)
    """
    type_upper = instance_type.upper()

    # 1. 게시판 인스턴스 수정
    if type_upper == "BOARD":
        board = db.query(BoardConfig).filter(BoardConfig.id == int(target_id)).first()
        if not board:
            raise HTTPException(status_code=404, detail="게시판 인스턴스를 찾을 수 없습니다.")

        if req.min_read_rank is not None:
            board.min_read_rank = req.min_read_rank
        if req.min_write_rank is not None:
            board.min_write_rank = req.min_write_rank
        if req.allow_groups is not None:
            board.allow_groups = req.allow_groups
        if req.deny_groups is not None:
            board.deny_groups = req.deny_groups

        db.commit()
        db.refresh(board)

        safe_log_audit(
            db=db,
            app_id="group_manage",
            log_type="SECURITY",
            action="INSTANCE_PERMISSION_CHANGED",
            title=f"게시판 권한 변경: [{board.name}] (R:{board.min_read_rank}/W:{board.min_write_rank})",
            user=current_user,
            severity="INFO",
            resource_type="board_config",
            resource_id=board.id,
            message=f"관리자 '{current_user.username}'이(가) 게시판 [{board.name}]의 4단계 권한(R:{board.min_read_rank}, W:{board.min_write_rank})을 수정했습니다.",
            metadata={"board_id": board.id, "min_read_rank": board.min_read_rank, "min_write_rank": board.min_write_rank}
        )

        return InstancePermissionItemRes(
            target_id=str(board.id),
            instance_type="BOARD",
            app_type="INSTANCE",
            title=f"{board.name} 게시판",
            slug=board.slug,
            parent_engine="게시판 (board)",
            icon="mdi:clipboard-text-outline",
            min_read_rank=board.min_read_rank,
            min_write_rank=board.min_write_rank,
            allow_groups=board.allow_groups or [],
            deny_groups=board.deny_groups or [],
        )

    # 2. 페이지 인스턴스 수정
    elif type_upper == "PAGE":
        page_obj = db.query(Page).filter(Page.id == int(target_id)).first()
        if not page_obj:
            raise HTTPException(status_code=404, detail="페이지 인스턴스를 찾을 수 없습니다.")

        if req.min_read_rank is not None:
            page_obj.min_rank = req.min_read_rank
        if req.allow_groups is not None:
            page_obj.allow_groups = req.allow_groups
        if req.deny_groups is not None:
            page_obj.deny_groups = req.deny_groups

        db.commit()
        db.refresh(page_obj)

        safe_log_audit(
            db=db,
            app_id="group_manage",
            log_type="SECURITY",
            action="INSTANCE_PERMISSION_CHANGED",
            title=f"페이지 권한 변경: [{page_obj.title}] (Rank:{page_obj.min_rank})",
            user=current_user,
            severity="INFO",
            resource_type="page",
            resource_id=page_obj.id,
            message=f"관리자 '{current_user.username}'이(가) 페이지 [{page_obj.title}]의 권한(최소랭크: {page_obj.min_rank})을 수정했습니다.",
            metadata={"page_id": page_obj.id, "min_rank": page_obj.min_rank}
        )

        return InstancePermissionItemRes(
            target_id=str(page_obj.id),
            instance_type="PAGE",
            app_type="CUSTOM",
            title=f"{page_obj.title} 페이지",
            slug=page_obj.slug,
            parent_engine="페이지 (page)",
            icon="mdi:file-document-edit-outline",
            min_read_rank=page_obj.min_rank if page_obj.min_rank is not None else 0,
            min_write_rank=9,
            allow_groups=page_obj.allow_groups or [],
            deny_groups=page_obj.deny_groups or [],
        )

    # 3. 단일 커스텀 앱 수정
    elif type_upper == "APP":
        app = db.query(AppRegistry).filter(AppRegistry.app_id == target_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")

        if req.min_read_rank is not None:
            app.min_read_rank = req.min_read_rank
        if req.min_write_rank is not None:
            app.min_write_rank = req.min_write_rank
        if req.allow_groups is not None:
            app.allow_groups = req.allow_groups
        if req.deny_groups is not None:
            app.deny_groups = req.deny_groups

        db.commit()
        db.refresh(app)

        safe_log_audit(
            db=db,
            app_id="group_manage",
            log_type="SECURITY",
            action="INSTANCE_PERMISSION_CHANGED",
            title=f"앱 권한 변경: [{app.name}] ({app.app_id}, R:{app.min_read_rank}/W:{app.min_write_rank})",
            user=current_user,
            severity="INFO",
            resource_type="app_registry",
            resource_id=app.app_id,
            message=f"관리자 '{current_user.username}'이(가) 앱 [{app.name}]의 4단계 권한(R:{app.min_read_rank}, W:{app.min_write_rank})을 수정했습니다.",
            metadata={"app_id": app.app_id, "min_read_rank": app.min_read_rank, "min_write_rank": app.min_write_rank}
        )

        return InstancePermissionItemRes(
            target_id=app.app_id,
            instance_type="APP",
            app_type=app.app_type or "SYSTEM",
            title=app.name,
            slug=app.app_id,
            frontend_route=app.frontend_route,
            parent_engine=f"단일 앱 ({app.app_type})",
            icon=app.icon_default or "mdi:apps",
            min_read_rank=app.min_read_rank,
            min_write_rank=app.min_write_rank,
            allow_groups=app.allow_groups or [],
            deny_groups=app.deny_groups or [],
        )

    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 인스턴스 타입입니다: '{instance_type}'")

