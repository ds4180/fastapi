from typing import List
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from core.audit import safe_log_audit
from core.deps import require_app_permission
from core.permission import ROOT_RANK, get_user_rank
from database import get_db
from domain.v1.admin import admin_schema
from models import SystemConfig, User, UserProfile, UserSession

router = APIRouter()

check_user_admin_read = require_app_permission("user_manage", action="read")
check_user_admin_write = require_app_permission("user_manage", action="write")
check_user_admin = check_user_admin_read  # 하위 호환 보존


@router.get("/users", response_model=List[admin_schema.UserAdminSchema])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read),
):
    """전체 유저 목록 조회 (관리자용)"""
    return db.query(User).options(joinedload(User.profile)).all()


@router.get("/users/{user_id}", response_model=admin_schema.UserAdminSchema)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read),
):
    """유저 상세 정보 조회"""
    user = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    return user


@router.put("/users/{user_id}/rank")
def update_user_rank(
    user_id: int,
    rank_in: admin_schema.UserRankUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write),
):
    """유저의 Rank 등급 및 승인 상태 수정"""
    if not (0 <= rank_in.rank_level <= 9):
        raise HTTPException(status_code=400, detail="랭크 레벨은 0부터 9 사이의 정수여야 합니다.")

    admin_rank = get_user_rank(admin)
    if admin_rank < ROOT_RANK:
        if rank_in.rank_level >= admin_rank:
            raise HTTPException(
                status_code=403,
                detail=f"자신의 권한 랭크(Lv.{admin_rank}) 이상의 랭크는 부여할 수 없습니다.",
            )
        if admin.id == user_id:
            raise HTTPException(status_code=400, detail="자신의 랭크는 직접 변경할 수 없습니다.")

    user = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    target_rank = get_user_rank(user)
    if target_rank >= ROOT_RANK and admin_rank < ROOT_RANK:
        raise HTTPException(status_code=403, detail="최고 관리자(root)의 랭크는 수정할 수 없습니다.")

    if not user.profile:
        user.profile = UserProfile(user_id=user.id)
        db.add(user.profile)

    old_rank = user.profile.rank_level
    user.profile.rank_level = rank_in.rank_level
    db.commit()

    from core.session import invalidate_user_session_caches
    invalidate_user_session_caches(db, user.id)

    # 🛡️ 전역 보안 감사로그 영구 기록
    safe_log_audit(
        db=db,
        app_id="user_manage",
        log_type="SECURITY",
        action="USER_RANK_CHANGED",
        title=f"사용자 '{user.username}' 권한 랭크 변경 (Lv.{old_rank} -> Lv.{rank_in.rank_level})",
        user=admin,
        severity="WARNING",
        resource_type="user",
        resource_id=user.id,
        message=f"관리자 '{admin.username}'(이)가 유저 '{user.username}'(ID: {user.id})의 랭크를 Lv.{old_rank}에서 Lv.{rank_in.rank_level}(으)로 변경했습니다.",
        diff_payload=[
            {
                "field": "rank_level",
                "from": old_rank,
                "to": rank_in.rank_level,
            }
        ],
        metadata={
            "target_username": user.username,
            "target_user_id": user.id,
            "old_rank": old_rank,
            "new_rank": rank_in.rank_level,
        },
    )

    return {"message": "success", "username": user.username, "new_rank": rank_in.rank_level}


@router.post("/users", response_model=admin_schema.UserAdminSchema)
def create_user_by_admin(
    user_in: admin_schema.UserCreateByAdmin,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write),
):
    """
    [관리자 전용 신규 사원 계정 직접 등록]
    중소기업 오피스 인트라넷을 위한 관리자 직접 계정 발급 API
    """
    from domain.user.user_crud import pwd_context

    admin_rank = get_user_rank(admin)
    if admin_rank < ROOT_RANK and user_in.rank_level >= admin_rank:
        raise HTTPException(
            status_code=403,
            detail=f"자신의 권한 랭크(Lv.{admin_rank}) 이상의 랭크는 부여할 수 없습니다.",
        )

    # 중복 검사 (아이디, 이메일)
    existing = (
        db.query(User)
        .filter((User.username == user_in.username) | (User.email == user_in.email))
        .first()
    )
    if existing:
        if existing.username == user_in.username:
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
        raise HTTPException(status_code=409, detail="이미 등록된 이메일 주소입니다.")

    hashed_pw = pwd_context.hash(user_in.password)
    new_user = User(
        username=user_in.username,
        password=hashed_pw,
        email=user_in.email,
        real_name=user_in.real_name,
    )
    db.add(new_user)
    db.flush()

    new_profile = UserProfile(
        user_id=new_user.id,
        rank_level=user_in.rank_level,
        primary_group=user_in.primary_group,
        secondary_groups=user_in.secondary_groups or [],
        employee_no=user_in.employee_no,
        is_active=True,
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_user)

    safe_log_audit(
        db=db,
        app_id="user_manage",
        log_type="SECURITY",
        action="USER_CREATED_BY_ADMIN",
        title=f"관리자에 의한 신규 사원 계정 생성: '{new_user.username}' (Lv.{user_in.rank_level})",
        user=admin,
        severity="INFO",
        resource_type="user",
        resource_id=new_user.id,
        message=f"관리자 '{admin.username}'이(가) 신규 사원 '{new_user.username}'(실명: {user_in.real_name or '미지정'}) 계정을 직접 생성했습니다. (부서: {user_in.primary_group or '소속없음'}, 랭크: Lv.{user_in.rank_level})",
        metadata={
            "created_user_id": new_user.id,
            "created_username": new_user.username,
            "rank_level": user_in.rank_level,
            "primary_group": user_in.primary_group,
            "admin_username": admin.username,
        },
    )

    return new_user


@router.delete("/users/{user_id}")
def delete_user_by_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write),
):
    """[관리자 전용] 유저 계정 소프트 삭제 (is_active=False 비활성화 & 권한 0 박탈 & 세션 만료)"""
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="자기 자신의 계정은 삭제할 수 없습니다.")

    target = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    target_rank = get_user_rank(target)
    admin_rank = get_user_rank(admin)
    if target_rank >= ROOT_RANK and admin_rank < ROOT_RANK:
        raise HTTPException(status_code=403, detail="최고 관리자(root) 계정은 삭제할 수 없습니다.")
    if admin_rank < ROOT_RANK and target_rank >= admin_rank:
        raise HTTPException(status_code=403, detail="자신보다 높거나 같은 랭크의 계정은 삭제할 수 없습니다.")

    # 🛡️ 소프트 삭제 원칙: DB 물리 삭제가 아닌 비활성화 플래그 및 랭크 회수
    if not target.profile:
        target.profile = UserProfile(user_id=target.id)
        db.add(target.profile)

    target.profile.is_active = False
    target.profile.rank_level = 0
    db.commit()

    # 활성 세션 즉시 만료 처리
    from domain.user.user_crud import kick_session

    active_sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == target.id,
            UserSession.status == "ACTIVE",
        )
        .all()
    )
    for s in active_sessions:
        kick_session(db, session_id=s.id)

    safe_log_audit(
        db=db,
        app_id="user_manage",
        log_type="SECURITY",
        action="USER_SOFT_DELETED",
        title=f"사용자 계정 소프트 삭제(비활성화): '{target.username}'",
        user=admin,
        severity="WARNING",
        resource_type="user",
        resource_id=user_id,
        message=f"관리자 '{admin.username}'이(가) 계정 '{target.username}'(ID: {user_id})을(를) 소프트 삭제(비활성화 및 랭크 박탈)했습니다.",
        metadata={"deleted_user_id": user_id, "deleted_username": target.username, "mode": "SOFT_DELETE"},
    )
    return {"message": "success", "deleted_user_id": user_id, "is_active": False}


@router.put("/users/{user_id}/restore")
def restore_user_by_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write),
):
    """[관리자 전용] 소프트 삭제된 유저 계정 복구 (is_active=True & Lv.1 정회원 복귀)"""
    target = db.query(User).options(joinedload(User.profile)).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    if not target.profile:
        target.profile = UserProfile(user_id=target.id)
        db.add(target.profile)

    target.profile.is_active = True
    target.profile.rank_level = 1
    db.commit()

    from core.session import invalidate_user_session_caches
    invalidate_user_session_caches(db, target.id)

    safe_log_audit(
        db=db,
        app_id="user_manage",
        log_type="SECURITY",
        action="USER_RESTORED",
        title=f"사용자 계정 복구(재활성화): '{target.username}'",
        user=admin,
        severity="INFO",
        resource_type="user",
        resource_id=user_id,
        message=f"관리자 '{admin.username}'이(가) 비활성화된 계정 '{target.username}'(ID: {user_id})을(를) 재활성화(Lv.1 복구)했습니다.",
        metadata={"restored_user_id": user_id, "restored_username": target.username},
    )
    return {"message": "success", "restored_user_id": user_id, "is_active": True}


@router.get("/users/config/register-mode")
def get_admin_register_mode(
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read),
):
    """[관리자용] 가입 모드 설정 조회 (ADMIN_ONLY, APPROVAL, OPEN)"""
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "AUTH_REGISTER_MODE").first()
    return {"register_mode": cfg.value if cfg and cfg.value else "ADMIN_ONLY"}


@router.put("/users/config/register-mode")
def update_admin_register_mode(
    mode_in: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write),
):
    """[관리자용] 가입 모드 설정 변경 (ADMIN_ONLY, APPROVAL, OPEN)"""
    new_mode = mode_in.get("register_mode", "ADMIN_ONLY")
    if new_mode not in ["ADMIN_ONLY", "APPROVAL", "OPEN"]:
        raise HTTPException(status_code=400, detail="유효하지 않은 가입 모드입니다. (ADMIN_ONLY, APPROVAL, OPEN)")

    cfg = db.query(SystemConfig).filter(SystemConfig.key == "AUTH_REGISTER_MODE").first()
    if not cfg:
        cfg = SystemConfig(
            key="AUTH_REGISTER_MODE",
            value=new_mode,
            description="회원가입 정책 (ADMIN_ONLY: 관리자 직접등록만, APPROVAL: 가입승인제, OPEN: 자유가입)",
        )
        db.add(cfg)
    else:
        cfg.value = new_mode

    db.commit()

    safe_log_audit(
        db=db,
        app_id="user_manage",
        log_type="SECURITY",
        action="REGISTER_MODE_CHANGED",
        title=f"회원가입 정책 모드 변경: {new_mode}",
        user=admin,
        severity="WARNING",
        resource_type="system_config",
        resource_id="AUTH_REGISTER_MODE",
        message=f"관리자 '{admin.username}'이(가) 시스템 가입 정책을 '{new_mode}'(으)로 변경했습니다.",
    )
    return {"message": "success", "register_mode": new_mode}
