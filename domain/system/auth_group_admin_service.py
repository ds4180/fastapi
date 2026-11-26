"""
============================================================================
[조직·권한 그룹 관제 비즈니스 서비스 (domain/system/auth_group_admin_service.py)]
============================================================================
- auth_group_router.py에 집중되어 있던 그룹 마스터 집계, Cascade 정화,
  사용자 주/부그룹 매칭, 앱·게시판·페이지 4단계 권한 수정 로직을 분리하고
  group_policy_service 동적 정책 및 JSONB 정합성(flag_modified)을 강제합니다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from domain.system.group_policy_service import get_group_manage_settings
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
)
from models import AppRegistry, BoardConfig, Group, Page, User, UserProfile


def remove_group_from_spec(spec: Any, target_code: str) -> Tuple[Any, bool]:
    """allow_groups 또는 deny_groups (단순 리스트 or JSONB 딕셔너리)에서 target_code를 안전하게 제거합니다."""
    if not spec:
        return spec, False
    if isinstance(spec, list):
        if target_code in spec:
            return [g for g in spec if g != target_code], True
        return spec, False
    if isinstance(spec, dict):
        changed = False
        new_dict: Dict[str, Any] = {}
        for action, groups in spec.items():
            if isinstance(groups, list):
                if target_code in groups:
                    new_dict[action] = [g for g in groups if g != target_code]
                    changed = True
                else:
                    new_dict[action] = list(groups)
            else:
                new_dict[action] = groups
        return (new_dict, True) if changed else (spec, False)
    return spec, False


def extract_all_groups_from_spec(spec: Any) -> Set[str]:
    """JSONB 듀얼 모드(리스트 또는 {read, write, all} 딕셔너리)에서 실제 그룹 코드만 안전하게 추출합니다."""
    if not spec:
        return set()
    if isinstance(spec, (list, set, tuple)):
        return {str(g) for g in spec if g}
    if isinstance(spec, dict):
        result: Set[str] = set()
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


def _build_group_usage_maps(db: Session) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, List[str]], Dict[str, List[str]]]:
    """
    회원(primary/secondary) 및 전체 권한 대상(AppRegistry + BoardConfig + Page)의
    그룹 연동 현황을 한 번에 집계합니다. (기존 BoardConfig/Page 누락 버그 해결)
    """
    primary_counts: Dict[str, int] = {}
    secondary_counts: Dict[str, int] = {}
    for p_grp, sec_list in db.query(UserProfile.primary_group, UserProfile.secondary_groups).all():
        if p_grp:
            primary_counts[p_grp] = primary_counts.get(p_grp, 0) + 1
        if isinstance(sec_list, list):
            for sec in sec_list:
                if sec:
                    secondary_counts[sec] = secondary_counts.get(sec, 0) + 1

    allow_map: Dict[str, List[str]] = {}
    deny_map: Dict[str, List[str]] = {}

    def _register(label: str, allow_spec: Any, deny_spec: Any) -> None:
        for g in extract_all_groups_from_spec(allow_spec):
            lst = allow_map.setdefault(g, [])
            if label not in lst:
                lst.append(label)
        for g in extract_all_groups_from_spec(deny_spec):
            lst = deny_map.setdefault(g, [])
            if label not in lst:
                lst.append(label)

    for a_name, a_allow, a_deny in db.query(AppRegistry.name, AppRegistry.allow_groups, AppRegistry.deny_groups).all():
        _register(a_name, a_allow, a_deny)

    for b_name, b_allow, b_deny in db.query(BoardConfig.name, BoardConfig.allow_groups, BoardConfig.deny_groups).all():
        _register(f"{b_name} 게시판", b_allow, b_deny)

    for p_title, p_allow, p_deny in (
        db.query(Page.title, Page.allow_groups, Page.deny_groups).filter(Page.is_deleted == False).all()
    ):
        _register(f"{p_title} 페이지", p_allow, p_deny)

    return primary_counts, secondary_counts, allow_map, deny_map


def _to_group_item_res(
    g: Group,
    primary_counts: Dict[str, int],
    secondary_counts: Dict[str, int],
    allow_map: Dict[str, List[str]],
    deny_map: Dict[str, List[str]],
) -> GroupItemRes:
    return GroupItemRes(
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
    )


# ==========================================================================
# 📂 1. 그룹 마스터 (Group View) 비즈니스 로직
# ==========================================================================


def list_group_masters(db: Session, group_type: Optional[str] = None) -> List[GroupItemRes]:
    query = db.query(Group)
    if group_type:
        query = query.filter(Group.group_type == group_type)
    groups = query.order_by(Group.group_type, Group.id).all()

    primary_counts, secondary_counts, allow_map, deny_map = _build_group_usage_maps(db)
    return [_to_group_item_res(g, primary_counts, secondary_counts, allow_map, deny_map) for g in groups]


def create_group_master_item(db: Session, req: GroupCreateReq) -> Tuple[Group, GroupItemRes]:
    settings = get_group_manage_settings(db)
    code_clean = req.code.strip()
    name_clean = req.name.strip()
    desc_clean = req.description.strip() if req.description else None

    if settings.get("require_group_description") and not desc_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 그룹 정책상 그룹 설명(용도) 입력이 필수입니다.",
        )

    existing = db.query(Group).filter(Group.code == code_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"이미 등록된 그룹 식별 코드입니다: '{code_clean}'",
        )

    new_group = Group(
        code=code_clean,
        name=name_clean,
        group_type=req.group_type,
        category=req.category,
        description=desc_clean,
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    res = GroupItemRes(
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
    return new_group, res


def update_group_master_item(db: Session, group_id: int, req: GroupUpdateReq) -> Tuple[Group, GroupItemRes]:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="그룹을 찾을 수 없습니다.")

    if req.name is not None:
        group.name = req.name.strip()
    if req.category is not None:
        group.category = req.category
    if req.description is not None:
        group.description = req.description.strip() or None

    db.commit()
    db.refresh(group)

    primary_counts, secondary_counts, allow_map, deny_map = _build_group_usage_maps(db)
    res = _to_group_item_res(group, primary_counts, secondary_counts, allow_map, deny_map)
    return group, res


def delete_group_master_item(db: Session, group_id: int) -> Tuple[str, str, Dict[str, int]]:
    """
    보호 그룹 잠금 및 사용 중 삭제 차단 정책을 검증한 뒤,
    허용 시 모든 회원 프로필·AppRegistry·BoardConfig·Page에서 Cascade 정화 후 삭제합니다.
    """
    settings = get_group_manage_settings(db)
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="삭제할 그룹을 찾을 수 없습니다.")

    deleted_code = group.code
    deleted_name = group.name

    protected_codes = set(settings.get("protected_group_codes") or [])
    if deleted_code in protected_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"보호 잠금된 핵심 그룹('{deleted_code}')은 삭제할 수 없습니다. [설정] 탭에서 보호 해제 후 진행하세요.",
        )

    primary_counts, secondary_counts, allow_map, deny_map = _build_group_usage_maps(db)
    member_refs = primary_counts.get(deleted_code, 0) + secondary_counts.get(deleted_code, 0)
    resource_refs = len(allow_map.get(deleted_code, [])) + len(deny_map.get(deleted_code, []))

    if settings.get("block_delete_in_use_group") and (member_refs > 0 or resource_refs > 0):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"사용 중인 그룹 삭제 차단 정책이 활성화되어 있습니다. "
                f"('{deleted_name}' 연결 현황: 회원 {member_refs}명, 앱·게시판·페이지 {resource_refs}곳)"
            ),
        )

    # 1. 주그룹 해제
    db.query(UserProfile).filter(UserProfile.primary_group == deleted_code).update(
        {"primary_group": None}, synchronize_session="fetch"
    )

    # 2. 부그룹 제거 (PostgreSQL JSONB / SQLite JSON 모두 안전 호환 + flag_modified)
    for prof in db.query(UserProfile).filter(UserProfile.secondary_groups.is_not(None)).all():
        if isinstance(prof.secondary_groups, list) and deleted_code in prof.secondary_groups:
            prof.secondary_groups = [g for g in prof.secondary_groups if g != deleted_code]
            flag_modified(prof, "secondary_groups")

    # 3. 앱 · 게시판 · 페이지 allow/deny 목록 정화
    for model_cls in (AppRegistry, BoardConfig, Page):
        for obj in db.query(model_cls).all():
            allow_cleaned, c1 = remove_group_from_spec(obj.allow_groups, deleted_code)
            deny_cleaned, c2 = remove_group_from_spec(obj.deny_groups, deleted_code)
            if c1:
                obj.allow_groups = allow_cleaned
                flag_modified(obj, "allow_groups")
            if c2:
                obj.deny_groups = deny_cleaned
                flag_modified(obj, "deny_groups")

    db.delete(group)
    db.commit()

    return deleted_code, deleted_name, {"member_refs": member_refs, "resource_refs": resource_refs}


# ==========================================================================
# 👤 2. 사용자 그룹 매칭 (User View) 비즈니스 로직
# ==========================================================================


def list_user_groups(db: Session, query: Optional[str] = None) -> List[UserGroupItemRes]:
    q = db.query(User).join(User.profile)
    if query and query.strip():
        search = f"%{query.strip()}%"
        q = q.filter(
            (User.username.ilike(search))
            | (User.real_name.ilike(search))
            | (User.email.ilike(search))
        )
    users = q.order_by(User.id).all()

    return [
        UserGroupItemRes(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            email=u.email,
            rank_level=u.rank(),
            primary_group=u.primary_group,
            secondary_groups=u.secondary_groups or [],
        )
        for u in users
    ]


def set_user_primary_group(db: Session, user_id: int, primary_group: Optional[str]) -> Optional[str]:
    settings = get_group_manage_settings(db)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    if primary_group:
        code = primary_group.strip()
        g = db.query(Group).filter(Group.code == code).first()
        if not g:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"존재하지 않는 그룹 코드입니다: '{code}'",
            )
        if settings.get("enforce_group_type_on_assign") and g.group_type != "PRIMARY":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"정책상 주그룹에는 PRIMARY 유형만 배정할 수 있습니다: '{code}' ({g.group_type})",
            )
        profile.primary_group = g.code
        # 주그룹과 동일한 부그룹이 이미 있으면 중복 방지 정책 적용 시 자동 정리
        if settings.get("prevent_duplicate_primary_secondary") and isinstance(profile.secondary_groups, list):
            if g.code in profile.secondary_groups:
                profile.secondary_groups = [s for s in profile.secondary_groups if s != g.code]
                flag_modified(profile, "secondary_groups")
    else:
        profile.primary_group = None

    db.commit()
    return profile.primary_group


def add_user_secondary_group_item(db: Session, user_id: int, code: str) -> Tuple[List[str], bool]:
    settings = get_group_manage_settings(db)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    clean_code = code.strip()
    g = db.query(Group).filter(Group.code == clean_code).first()
    if not g:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"존재하지 않는 그룹 코드입니다: '{clean_code}'",
        )

    if settings.get("enforce_group_type_on_assign") and g.group_type != "SECONDARY":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"정책상 부그룹에는 SECONDARY 유형만 배정할 수 있습니다: '{clean_code}' ({g.group_type})",
        )

    if settings.get("prevent_duplicate_primary_secondary") and profile.primary_group == clean_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"이미 주그룹으로 배정된 코드('{clean_code}')는 부그룹으로 중복 추가할 수 없습니다.",
        )

    current_sec = list(profile.secondary_groups or [])
    if clean_code in current_sec:
        return current_sec, False

    max_sec = int(settings.get("max_secondary_groups_per_user", 10))
    if len(current_sec) >= max_sec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"사용자 1인당 최대 부그룹 배정 한도({max_sec}개)를 초과했습니다.",
        )

    current_sec.append(clean_code)
    profile.secondary_groups = current_sec
    flag_modified(profile, "secondary_groups")
    db.commit()
    return current_sec, True


def remove_user_secondary_group_item(db: Session, user_id: int, code: str) -> Tuple[List[str], bool]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    current_sec = list(profile.secondary_groups or [])
    if code not in current_sec:
        return current_sec, False

    updated = [g for g in current_sec if g != code]
    profile.secondary_groups = updated
    flag_modified(profile, "secondary_groups")
    db.commit()
    return updated, True


def set_user_groups_batch(db: Session, user_id: int, req: UserGroupBatchReq) -> Tuple[Optional[str], List[str]]:
    """사용자 주그룹·부그룹 일괄 설정 (코드 실존 검증 + 정책 검증 적용)"""
    settings = get_group_manage_settings(db)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자 프로필을 찾을 수 없습니다.")

    all_codes_in_db = {g.code: g.group_type for g in db.query(Group.code, Group.group_type).all()}

    new_primary = req.primary_group.strip() if req.primary_group else None
    if new_primary:
        if new_primary not in all_codes_in_db:
            raise HTTPException(status_code=400, detail=f"존재하지 않는 주그룹 코드입니다: '{new_primary}'")
        if settings.get("enforce_group_type_on_assign") and all_codes_in_db[new_primary] != "PRIMARY":
            raise HTTPException(status_code=400, detail=f"주그룹에는 PRIMARY 유형만 배정할 수 있습니다: '{new_primary}'")

    dedup_sec: List[str] = []
    for raw_c in req.secondary_groups or []:
        c = str(raw_c or "").strip()
        if not c or c in dedup_sec:
            continue
        if c not in all_codes_in_db:
            raise HTTPException(status_code=400, detail=f"존재하지 않는 부그룹 코드입니다: '{c}'")
        if settings.get("enforce_group_type_on_assign") and all_codes_in_db[c] != "SECONDARY":
            raise HTTPException(status_code=400, detail=f"부그룹에는 SECONDARY 유형만 배정할 수 있습니다: '{c}'")
        if settings.get("prevent_duplicate_primary_secondary") and c == new_primary:
            continue
        dedup_sec.append(c)

    max_sec = int(settings.get("max_secondary_groups_per_user", 10))
    if len(dedup_sec) > max_sec:
        raise HTTPException(
            status_code=400,
            detail=f"사용자 1인당 최대 부그룹 배정 한도({max_sec}개)를 초과했습니다.",
        )

    profile.primary_group = new_primary
    profile.secondary_groups = dedup_sec
    flag_modified(profile, "secondary_groups")
    db.commit()
    return profile.primary_group, profile.secondary_groups


# ==========================================================================
# 📱 3. 앱 & 통합 인스턴스 권한 (App / Instance View) 비즈니스 로직
# ==========================================================================


def list_app_permissions(db: Session) -> List[AppPermissionItemRes]:
    apps = db.query(AppRegistry).order_by(AppRegistry.app_id).all()
    return [
        AppPermissionItemRes(
            app_id=a.app_id,
            name=a.name,
            title=a.title,
            description=a.description,
            app_type=a.app_type,
            min_read_rank=a.min_read_rank,
            min_write_rank=a.min_write_rank,
            allow_groups=a.allow_groups or [],
            deny_groups=a.deny_groups or [],
        )
        for a in apps
    ]


def update_app_permission_item(db: Session, app_id: str, req: AppPermissionsUpdateReq) -> Tuple[AppRegistry, AppPermissionItemRes]:
    app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="앱을 찾을 수 없습니다.")

    if req.min_read_rank is not None:
        app.min_read_rank = req.min_read_rank
    if req.min_write_rank is not None:
        app.min_write_rank = req.min_write_rank
    if req.allow_groups is not None:
        app.allow_groups = req.allow_groups
        flag_modified(app, "allow_groups")
    if req.deny_groups is not None:
        app.deny_groups = req.deny_groups
        flag_modified(app, "deny_groups")

    db.commit()
    db.refresh(app)

    res = AppPermissionItemRes(
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
    return app, res


def list_all_instance_permissions(db: Session) -> List[InstancePermissionItemRes]:
    settings = get_group_manage_settings(db)
    page_write_rank = int(settings.get("default_page_write_rank", 9))

    result: List[InstancePermissionItemRes] = []

    for b in db.query(BoardConfig).order_by(BoardConfig.id).all():
        result.append(
            InstancePermissionItemRes(
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
            )
        )

    for p in db.query(Page).filter(Page.is_deleted == False).order_by(Page.id).all():
        result.append(
            InstancePermissionItemRes(
                target_id=str(p.id),
                instance_type="PAGE",
                app_type="CUSTOM",
                title=f"{p.title} 페이지",
                slug=p.slug,
                parent_engine="페이지 (page)",
                icon="mdi:file-document-edit-outline",
                min_read_rank=p.min_rank if p.min_rank is not None else 0,
                min_write_rank=page_write_rank,
                allow_groups=p.allow_groups or [],
                deny_groups=p.deny_groups or [],
            )
        )

    for a in db.query(AppRegistry).filter(AppRegistry.app_type != "INSTANCE").order_by(AppRegistry.app_id).all():
        result.append(
            InstancePermissionItemRes(
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
            )
        )

    return result


def update_instance_permission_item(
    db: Session,
    instance_type: str,
    target_id: str,
    req: InstancePermissionUpdateReq,
) -> Tuple[InstancePermissionItemRes, Dict[str, Any]]:
    settings = get_group_manage_settings(db)
    page_write_rank = int(settings.get("default_page_write_rank", 9))
    type_upper = instance_type.upper()

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
            flag_modified(board, "allow_groups")
        if req.deny_groups is not None:
            board.deny_groups = req.deny_groups
            flag_modified(board, "deny_groups")

        db.commit()
        db.refresh(board)
        res = InstancePermissionItemRes(
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
        audit_meta = {
            "resource_type": "board_config",
            "resource_id": str(board.id),
            "title": f"게시판 권한 변경: [{board.name}] (R:{board.min_read_rank}/W:{board.min_write_rank})",
            "meta": {"board_id": board.id, "min_read_rank": board.min_read_rank, "min_write_rank": board.min_write_rank},
        }
        return res, audit_meta

    if type_upper == "PAGE":
        page_obj = db.query(Page).filter(Page.id == int(target_id)).first()
        if not page_obj:
            raise HTTPException(status_code=404, detail="페이지 인스턴스를 찾을 수 없습니다.")

        if req.min_read_rank is not None:
            page_obj.min_rank = req.min_read_rank
        if req.allow_groups is not None:
            page_obj.allow_groups = req.allow_groups
            flag_modified(page_obj, "allow_groups")
        if req.deny_groups is not None:
            page_obj.deny_groups = req.deny_groups
            flag_modified(page_obj, "deny_groups")

        db.commit()
        db.refresh(page_obj)
        res = InstancePermissionItemRes(
            target_id=str(page_obj.id),
            instance_type="PAGE",
            app_type="CUSTOM",
            title=f"{page_obj.title} 페이지",
            slug=page_obj.slug,
            parent_engine="페이지 (page)",
            icon="mdi:file-document-edit-outline",
            min_read_rank=page_obj.min_rank if page_obj.min_rank is not None else 0,
            min_write_rank=page_write_rank,
            allow_groups=page_obj.allow_groups or [],
            deny_groups=page_obj.deny_groups or [],
        )
        audit_meta = {
            "resource_type": "page",
            "resource_id": str(page_obj.id),
            "title": f"페이지 권한 변경: [{page_obj.title}] (Rank:{page_obj.min_rank})",
            "meta": {"page_id": page_obj.id, "min_rank": page_obj.min_rank},
        }
        return res, audit_meta

    if type_upper == "APP":
        app = db.query(AppRegistry).filter(AppRegistry.app_id == target_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")

        if req.min_read_rank is not None:
            app.min_read_rank = req.min_read_rank
        if req.min_write_rank is not None:
            app.min_write_rank = req.min_write_rank
        if req.allow_groups is not None:
            app.allow_groups = req.allow_groups
            flag_modified(app, "allow_groups")
        if req.deny_groups is not None:
            app.deny_groups = req.deny_groups
            flag_modified(app, "deny_groups")

        db.commit()
        db.refresh(app)
        res = InstancePermissionItemRes(
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
        audit_meta = {
            "resource_type": "app_registry",
            "resource_id": str(app.app_id),
            "title": f"앱 권한 변경: [{app.name}] ({app.app_id}, R:{app.min_read_rank}/W:{app.min_write_rank})",
            "meta": {"app_id": app.app_id, "min_read_rank": app.min_read_rank, "min_write_rank": app.min_write_rank},
        }
        return res, audit_meta

    raise HTTPException(status_code=400, detail=f"지원하지 않는 인스턴스 유형입니다: {instance_type}")
