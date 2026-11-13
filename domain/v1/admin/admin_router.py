from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import (
    User, UserProfile, BoardConfig, Post, Menu, SystemConfig, AppRegistry,
    DayOff, Page, ServiceRegistry, ServiceEngine, ServiceApp, ServiceInstance,
    RouteMaster, RouteTimetable, SystemTask, AuditLog, UserSession, MiniappItem
)
from core.deps import (
    get_current_user,
    get_current_user_optional,
    RankChecker,
    check_rank,
    require_app_permission,
)
from core.audit import safe_log_audit
from core.permission import can_access_app, evaluate_permission, get_user_rank, ROOT_RANK
from domain.v1.admin import admin_schema
from typing import List, Optional, Any
from datetime import date, datetime, timedelta
import re
import models

router = APIRouter(
    prefix="/admin",
    tags=["admin_v1"]
)

API_VERSION_PREFIX = "/v1"

# 🏛️ AppRegistry 거버넌스 연동 시스템 앱별 전용 인가 가드 (실시간 4단계 권한 통일)
check_admin = require_app_permission("dashboard", action="read") # 대시보드 관제센터 전용 거버넌스 가드
check_user_admin_read = require_app_permission("user_manage", action="read")
check_user_admin_write = require_app_permission("user_manage", action="write")
check_user_admin = check_user_admin_read # 하위 호환 보존
check_app_admin = require_app_permission("apps")
check_menu_admin_read = require_app_permission("menu", action="read")
check_menu_admin_write = require_app_permission("menu", action="write")
check_menu_admin = check_menu_admin_read # 하위 호환 보존
check_board_admin = require_app_permission("boards", action="read")
check_board_admin_write = require_app_permission("boards", action="write")
check_service_admin = require_app_permission("services", action="read")
check_service_admin_write = require_app_permission("services", action="write")
check_dayoff_admin = require_app_permission("dayoff", action="read")
check_dayoff_admin_write = require_app_permission("dayoff", action="write")
check_config_admin_read = require_app_permission("config", action="read")
check_config_admin_write = require_app_permission("config", action="write")
check_config_admin = check_config_admin_read # 하위 호환 보존
check_push_admin = require_app_permission("pushs", action="read")
check_push_admin_write = require_app_permission("pushs", action="write")
check_route_master_admin = require_app_permission("route_master", action="read")
check_route_master_admin_write = require_app_permission("route_master", action="write")
check_dispatch_admin = require_app_permission("dispatch", action="read")
check_dispatch_admin_write = require_app_permission("dispatch", action="write")

@router.get("/dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """
    [코어 통합 관제탑 대시보드 요약 정보]
    시스템 코어 엔진(자율신경계 태스크, 관제/감사로그, 세션/근무, 지시사항 인지율) 종합 지표
    """
    now = datetime.now()
    today = now.date()
    yesterday = now - timedelta(hours=24)

    # 1. 자율신경계 태스크 상태
    task_pending = db.query(SystemTask).filter(SystemTask.status == "PENDING").count()
    task_running = db.query(SystemTask).filter(SystemTask.status == "RUNNING").count()
    task_failed = db.query(SystemTask).filter(SystemTask.status == "FAILED").count()
    next_task = db.query(SystemTask.scheduled_at).filter(
        SystemTask.status == "PENDING"
    ).order_by(SystemTask.scheduled_at.asc()).first()
    next_task_str = next_task[0].strftime("%Y-%m-%d %H:%M") if next_task and next_task[0] else None

    # 2. 통합 관제 & 감사로그 (최근 24시간 보안 침해 및 시스템 에러)
    security_breach_24h = db.query(AuditLog).filter(
        AuditLog.log_type == "SECURITY",
        AuditLog.created_at >= yesterday
    ).count()
    error_log_24h = db.query(AuditLog).filter(
        AuditLog.log_type == "ERROR",
        AuditLog.created_at >= yesterday
    ).count()

    # 실시간 활성 세션 (Active Sessions)
    active_sessions = db.query(UserSession).filter(UserSession.status == "ACTIVE").count()

    # 3. 오늘 근무 및 휴무 비율
    dayoff_count = db.query(DayOff).filter(
        DayOff.date == today,
        DayOff.status == "APPROVED",
        DayOff.is_deleted == False
    ).count()
    active_user_count = db.query(UserProfile).filter(UserProfile.is_active == True).count()
    working_count = max(0, active_user_count - dayoff_count)

    # 4. 현장 지시사항 미확인 인지율 감시
    unconfirmed_instructions = db.query(MiniappItem).filter(
        MiniappItem.category == "INSTRUCTION",
        MiniappItem.status.notin_(["CONFIRMED", "COMPLETED"])
    ).count()

    # 5. 기존 기본 메타 카운트 (하위 호환성 100% 유지)
    user_count = db.query(User).count()
    board_count = db.query(BoardConfig).count()
    post_count = db.query(Post).count()
    app_count = db.query(AppRegistry).count()

    # 6. 실시간 시스템/비즈니스 앱 권한 메타데이터 (AppRegistry 실시간 연동)
    all_registered_apps = db.query(AppRegistry).all()
    apps_meta = [
        {
            "app_id": a.app_id,
            "name": a.name,
            "min_read_rank": a.min_read_rank if a.min_read_rank is not None else 4,
            "min_write_rank": a.min_write_rank if a.min_write_rank is not None else 4,
            "allow_groups": a.allow_groups or [],
            "deny_groups": a.deny_groups or [],
            "is_active": a.is_active
        }
        for a in all_registered_apps
    ]

    return {
        "admin_name": admin.real_name or admin.username,
        "task_engine": {
            "is_healthy": task_failed == 0,
            "pending_count": task_pending,
            "running_count": task_running,
            "failed_count": task_failed,
            "next_scheduled_task": next_task_str
        },
        "observability": {
            "security_breach_24h": security_breach_24h,
            "error_log_24h": error_log_24h,
            "active_sessions": active_sessions
        },
        "duty_status": {
            "working_count": working_count,
            "dayoff_count": dayoff_count,
            "active_user_count": active_user_count
        },
        "instruction_watchdog": {
            "unconfirmed_count": unconfirmed_instructions
        },
        "watchdog_status": {
            "enabled": True,
            "fail_threshold": 3,
            "security_alert": True
        },
        # 하위 호환 필드
        "user_count": user_count,
        "board_count": board_count,
        "post_count": post_count,
        "app_count": app_count,
        # 실시간 앱 권한 명부
        "system_apps": apps_meta
    }

# --- User Management (유저 관리 - admin_user_manage 거버넌스 연동) ---

@router.get("/users", response_model=List[admin_schema.UserAdminSchema])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read)
):
    """전체 유저 목록 조회 (관리자용)"""
    return db.query(User).options(joinedload(User.profile)).all()

@router.get("/users/{user_id}", response_model=admin_schema.UserAdminSchema)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read)
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
    admin: User = Depends(check_user_admin_write)
):
    """유저의 Rank 등급 및 승인 상태 수정"""
    if not (0 <= rank_in.rank_level <= 9):
        raise HTTPException(status_code=400, detail="랭크 레벨은 0부터 9 사이의 정수여야 합니다.")

    admin_rank = get_user_rank(admin)
    if admin_rank < ROOT_RANK:
        if rank_in.rank_level >= admin_rank:
            raise HTTPException(
                status_code=403,
                detail=f"자신의 권한 랭크(Lv.{admin_rank}) 이상의 랭크는 부여할 수 없습니다."
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
        diff_payload=[{
            "field": "rank_level",
            "from": old_rank,
            "to": rank_in.rank_level
        }],
        metadata={
            "target_username": user.username,
            "target_user_id": user.id,
            "old_rank": old_rank,
            "new_rank": rank_in.rank_level
        }
    )

    return {"message": "success", "username": user.username, "new_rank": rank_in.rank_level}

@router.post("/users", response_model=admin_schema.UserAdminSchema)
def create_user_by_admin(
    user_in: admin_schema.UserCreateByAdmin,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write)
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
            detail=f"자신의 권한 랭크(Lv.{admin_rank}) 이상의 랭크는 부여할 수 없습니다."
        )

    # 중복 검사 (아이디, 이메일)
    existing = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
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
            "admin_username": admin.username
        }
    )

    return new_user

@router.delete("/users/{user_id}")
def delete_user_by_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write)
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
    active_sessions = db.query(UserSession).filter(
        UserSession.user_id == target.id,
        UserSession.status == "ACTIVE"
    ).all()
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
        metadata={"deleted_user_id": user_id, "deleted_username": target.username, "mode": "SOFT_DELETE"}
    )
    return {"message": "success", "deleted_user_id": user_id, "is_active": False}

@router.put("/users/{user_id}/restore")
def restore_user_by_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write)
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
        metadata={"restored_user_id": user_id, "restored_username": target.username}
    )
    return {"message": "success", "restored_user_id": user_id, "is_active": True}

@router.get("/users/config/register-mode")
def get_admin_register_mode(
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_read)
):
    """[관리자용] 가입 모드 설정 조회 (ADMIN_ONLY, APPROVAL, OPEN)"""
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "AUTH_REGISTER_MODE").first()
    return {"register_mode": cfg.value if cfg and cfg.value else "ADMIN_ONLY"}

@router.put("/users/config/register-mode")
def update_admin_register_mode(
    mode_in: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_user_admin_write)
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
            description="회원가입 정책 (ADMIN_ONLY: 관리자 직접등록만, APPROVAL: 가입승인제, OPEN: 자유가입)"
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
        message=f"관리자 '{admin.username}'이(가) 시스템 가입 정책을 '{new_mode}'(으)로 변경했습니다."
    )
    return {"message": "success", "register_mode": new_mode}

# --- [v1.5] App Registry 관리 API (admin_apps 거버넌스 연동) ---

@router.get("/apps", response_model=List[admin_schema.AppRegistrySchema])
def get_all_apps(db: Session = Depends(get_db), admin: User = Depends(check_app_admin)):
    """시스템에 등록된 모든 App 엔진 목록 조회 (관리자용)"""
    from domain.system.app_service import DEFAULT_SYSTEM_APPS

    # 시스템 앱의 공식 명칭(title, name, icon) 및 시스템 앱 타입(SYSTEM, CUSTOM, INSTANCE) 동기화
    sys_map = {a["app_id"]: a for a in DEFAULT_SYSTEM_APPS}
    all_apps = db.query(AppRegistry).order_by(AppRegistry.app_id).all()
    needs_commit = False
    for app in all_apps:
        meta = sys_map.get(app.app_id)
        if meta:
            if meta.get("title") and app.title != meta["title"]:
                app.title = meta["title"]
                needs_commit = True
            if meta.get("name") and app.name != meta["name"]:
                app.name = meta["name"]
                needs_commit = True
            if meta.get("icon_default") and app.icon_default != meta["icon_default"]:
                app.icon_default = meta["icon_default"]
                needs_commit = True
            # 시스템 앱의 경우 기본 app_type(SYSTEM, CUSTOM, INSTANCE) 동기화
            if meta.get("app_type") and app.app_type != meta["app_type"]:
                app.app_type = meta["app_type"]
                needs_commit = True
    if needs_commit:
        db.commit()
        all_apps = db.query(AppRegistry).order_by(AppRegistry.app_id).all()

    return all_apps

@router.get("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def get_app_detail(
    app_id: str, 
    db: Session = Depends(get_db),
    admin: User = Depends(check_app_admin)
):
    """
    [특정 앱의 메타데이터 및 설정 스키마 상세 조회]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9) 적용
    - 내부 권한 그룹(allow/deny_groups) 및 설정 스키마의 무단 노출을 방지하기 위해 관리자 권한 필수
    """
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="등록되지 않은 앱 엔진입니다.")
    return db_app

@router.post("/apps", response_model=admin_schema.AppRegistrySchema)
def create_app_registry(
    app_in: admin_schema.AppRegistryCreate, 
    db: Session = Depends(get_db), 
    admin: User = Depends(check_app_admin)
):
    """
    [신규 App 엔진 및 메타데이터 등록]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 중복 식별자(app_id) 방어 및 Pydantic 엄격 검증(app_type 4대 분류, frontend_route 포맷)
    - 📜 최고 관리자 등록 행위(APP_REGISTERED) 보안 감사로그(AuditLog) 영구 보존
    """
    # 1. 중복 ID 체크 (선점 방지)
    existing = db.query(AppRegistry).filter(AppRegistry.app_id == app_in.app_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 앱 식별자입니다.")
    
    payload = app_in.dict()
    
    # 2. 신규 AppRegistry DB 레코드 영속화
    db_app = AppRegistry(**payload)
    db.add(db_app)
    db.commit()
    db.refresh(db_app)

    # 3. 📜 [보안 감사로그 영구 기록]
    safe_log_audit(
        db=db,
        app_id="apps",
        log_type="SECURITY",
        action="APP_REGISTERED",
        title=f"신규 앱 엔진 등록: {db_app.title or db_app.name} ({db_app.app_id})",
        user=admin,
        resource_type="app_registry",
        resource_id=db_app.app_id,
        message=f"유형: {db_app.app_type}, 진입로: {db_app.frontend_route}, 랭크: R{db_app.min_read_rank}/W{db_app.min_write_rank}",
        metadata={
            "app_id": db_app.app_id,
            "app_type": db_app.app_type,
            "min_read_rank": db_app.min_read_rank,
            "min_write_rank": db_app.min_write_rank,
            "allow_groups": db_app.allow_groups,
            "deny_groups": db_app.deny_groups,
        }
    )

    return db_app

@router.patch("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def update_app_registry(
    app_id: str, 
    app_in: admin_schema.AppRegistryUpdate, 
    db: Session = Depends(get_db), 
    admin: User = Depends(check_app_admin)
):
    """
    [App 엔진 메타데이터 수정 (권한, 경로, 자치관리자 등)]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 🚨 SYSTEM 필수 앱 보호: app_type 변경 시도 및 is_active=False 비활성화 원천 차단 (403)
    - 📜 변경 전/후 필드 차이점(Diff-Patch) 자동 추적 및 보안/시스템 감사로그(AuditLog) 영구 보존
    """
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    
    # 1. 전달된 필드만 추출 (exclude_unset=True)
    update_data = app_in.dict(exclude_unset=True)

    # 2. 🚨 [SYSTEM 필수 관제 앱 철벽 방어선]
    # SYSTEM 타입 앱은 시스템 척추이므로 임의로 타입을 바꾸거나 비활성화할 수 없습니다.
    if db_app.app_type == "SYSTEM":
        if "app_type" in update_data and update_data["app_type"] != "SYSTEM":
            raise HTTPException(
                status_code=403, 
                detail="SYSTEM 앱의 유형(app_type)은 시스템 필수 규격이므로 변경할 수 없습니다."
            )
        if "is_active" in update_data and update_data["is_active"] is False:
            raise HTTPException(
                status_code=403, 
                detail="SYSTEM 앱은 시스템 필수 관제 앱이므로 비활성화할 수 없습니다."
            )

    # 3. 🔍 변경 전/후 Diff 캡처 및 필드 갱신
    diff_list = []
    for key, value in update_data.items():
        old_val = getattr(db_app, key, None)
        if old_val != value:
            diff_list.append({
                "field": key,
                "from": old_val,
                "to": value
            })
            setattr(db_app, key, value)
    
    db.commit()
    db.refresh(db_app)

    # 4. 📜 [보안 및 설정 감사로그 영구 기록]
    if diff_list:
        # 보안 등급이나 접근 권한, 활성화 여부 변경 시 SECURITY 로그로 격상 분류
        is_security_change = any(
            f["field"] in ["min_read_rank", "min_write_rank", "allow_groups", "deny_groups", "is_active", "app_type"] 
            for f in diff_list
        )
        safe_log_audit(
            db=db,
            app_id="apps",
            log_type="SECURITY" if is_security_change else "SYSTEM",
            action="APP_UPDATED",
            title=f"앱 엔진 메타데이터 수정: {db_app.title or db_app.name} ({db_app.app_id})",
            user=admin,
            resource_type="app_registry",
            resource_id=db_app.app_id,
            message=f"{len(diff_list)}개 항목 변경 완료: " + ", ".join([d["field"] for d in diff_list]),
            diff_payload=diff_list,
            metadata={"updated_fields": list(update_data.keys())}
        )

    return db_app

@router.delete("/apps/{app_id}")
def delete_app(app_id: str, db: Session = Depends(get_db), admin: User = Depends(check_app_admin)):
    """
    [앱 등록 해제 및 제거]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 🚨 SYSTEM 앱은 시스템 필수 관제 앱이므로 삭제 영구 차단 (403)
    - 📜 최고 관리자 앱 삭제 행위(APP_DELETED) 보안 감사로그(AuditLog, WARN) 영구 보존
    """
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    if db_app.app_type == "SYSTEM":
        raise HTTPException(status_code=403, detail="SYSTEM 앱은 시스템 필수 관제 앱이므로 삭제할 수 없습니다.")
    
    app_name = db_app.title or db_app.name
    app_type = db_app.app_type

    db.delete(db_app)
    db.commit()

    # 📜 [보안 감사로그 영구 기록]
    safe_log_audit(
        db=db,
        app_id="apps",
        log_type="SECURITY",
        action="APP_DELETED",
        title=f"앱 엔진 삭제 완료: {app_name} ({app_id})",
        user=admin,
        severity="WARN",
        resource_type="app_registry",
        resource_id=app_id,
        message=f"유형: {app_type} 앱이 시스템에서 영구 삭제되었습니다.",
        metadata={"app_id": app_id, "app_type": app_type}
    )

    return {"message": "success"}

# --- Menu Management (지능형 메뉴 관리) ---

# 📄 PAGES 레이어로 이관된 순수 정적/데모 페이지 경로 매핑
MIGRATED_PAGES_MAP = {
    "/v1/custom/chart": "/v1/pages/chart",
    "/v1/custom/canvas": "/v1/pages/canvas",
    "/v1/custom/uploadfile": "/v1/pages/uploadfile",
}

def resolve_menu_url(menu: Menu, db: Session) -> str:
    """
    [v3.0 헌법 표준 단일 원칙 주소 조립기]
    
    🏛️ 사용자 정립 절대 원칙:
    1. 고정 URL / 폴더 / 구분선: URL 또는 '#'
    2. 관리자 기능이 필요한 모든 경우: 무조건 /v1/admin/{clean_id} (CUSTOM/INSTANCE 불문 관리자 직행)
    3. 사용자 화면:
       - CUSTOM: /v1/custom/{clean_id}
       - INSTANCE: /v1/app/{clean_id}/{slug}
       - PAGES / PAGE: /v1/pages/{slug or page_id}
    """
    # 1. 🔗 수동 입력 URL 및 폴더/구분선
    if menu.link_type == "URL":
        raw_url = menu.external_url or "#"
        # 🩹 부모 접합 버그로 오염된 '#/' 접두사 자동 자가치유
        if raw_url.startswith("#/") and len(raw_url) > 2:
            raw_url = raw_url[1:]
            menu.external_url = raw_url
            db.commit()
        if raw_url in MIGRATED_PAGES_MAP:
            menu.external_url = MIGRATED_PAGES_MAP[raw_url]
            db.commit()
            return menu.external_url
        return raw_url

    if menu.link_type in ["FOLDER", "DIVIDER"]:
        return "#"

    # 2. ⚙️ 앱 엔진 기반 메뉴 경로 판별
    if menu.app_id:
        clean_id = menu.app_id
        instance_id = str(menu.app_instance_id) if menu.app_instance_id is not None else ""

        # 🏛️ [대원칙]: 어느 메뉴이든 '관리자 기능이 필요한 경우' 관리자 전용 경로로 직행!
        # 1. link_type이 SYSTEM인 순수 시스템 관리 메뉴
        # 2. 인스턴스 관리자 모드(instance_id == "-1")인 경우
        is_admin_mode = (
            menu.link_type == "SYSTEM" 
            or instance_id == "-1"
        )

        # 🌟 [단일 진실 공급원 SSOT]: AppRegistry에 정의된 공식 frontend_route 최우선 바인딩
        app_reg = db.query(AppRegistry).filter(AppRegistry.app_id == clean_id).first()

        if is_admin_mode:
            if app_reg and app_reg.frontend_route:
                return app_reg.frontend_route
            if clean_id in ["dashboard", ""]:
                return f"{API_VERSION_PREFIX}/admin"
            return f"{API_VERSION_PREFIX}/admin/{clean_id}"

        # 👤 [사용자 화면]: 각 앱의 타입에 맞는 전용 거처로 1:1 직행 (CUSTOM은 예외 없이 /v1/custom/{clean_id})
        if menu.link_type == "CUSTOM":
            return f"{API_VERSION_PREFIX}/custom/{clean_id}"

        if menu.link_type in ["INSTANCE", "APP"]:
            slug = get_instance_slug(menu, db)
            # 게시판 등 다중 인스턴스: 특정 개체는 단수형(/v1/app/board/{slug}), 허브는 복수형(/v1/app/boards)
            if slug and slug != "-1":
                instance_prefix = clean_id.rstrip("s") if clean_id.endswith("s") else clean_id
                return f"{API_VERSION_PREFIX}/app/{instance_prefix}/{slug}"
            return f"{API_VERSION_PREFIX}/app/{clean_id}"

    # 3. 📄 정적 콘텐츠 레이어 (PAGE / PAGES 직접 링크)
    if menu.link_type in ["PAGE", "PAGES"] and (menu.page_id or menu.app_id):
        target = menu.page_id or menu.app_id
        slug = get_instance_slug(menu, db)
        if slug and slug != "-1":
            return f"{API_VERSION_PREFIX}/pages/{slug}"
        return f"{API_VERSION_PREFIX}/pages"

    return menu.external_url or "#"

def get_instance_slug(menu: Menu, db: Session) -> Optional[str]:
    """
    [인스턴스 ID -> 슬러그(Slug) 변환 헬퍼 (PostgreSQL 타입 안전 가드)]
    - INSTANCE 앱(board, page 등)에 연결된 인스턴스 식별자를 슬러그(slug)로 변환합니다.
    - menu.app_instance_id가 정수형 ID인 경우 DB 조회, 이미 문자열 슬러그인 경우 즉시 반환하여
      PostgreSQL 'invalid input syntax for type integer' 예외(500 에러)를 원천 차단합니다.
    """
    if menu.app_instance_id is None:
        return None
    raw_val = menu.app_instance_id
    if raw_val == -1 or str(raw_val) == "-1":
        return "-1"

    clean_id = menu.app_id or ""

    # 1. 숫자형 정수 ID인지 안전하게 판별
    int_id = None
    try:
        int_id = int(raw_val)
    except (ValueError, TypeError):
        int_id = None

    # 2. 게시판(Board) 인스턴스 슬러그 역추적
    if clean_id in ['board', 'boards']:
        if int_id is not None:
            board = db.query(BoardConfig).filter(BoardConfig.id == int_id).first()
            return board.slug if board else str(raw_val)
        return str(raw_val)

    # 3. 페이지(Page) 인스턴스 슬러그 역추적
    if clean_id in ['page', 'pages'] or menu.link_type in ['PAGE', 'PAGES']:
        if int_id is not None:
            page_obj = db.query(Page).filter(Page.id == int_id).first()
            return page_obj.slug if page_obj else str(raw_val)
        return str(raw_val)

    return str(raw_val)

def filter_menu_tree(
    menus: List[Menu],
    current_user: Optional[User],
    db: Session,
    bypass_auth: bool = False
):
    """
    [4단계 권한 기반 재귀적 메뉴 필터링 및 동적 URL 주입]
    1. root(9) 인가? ➔ 무조건 노출
    2. 메뉴의 deny_groups 에 사용자의 부그룹/주그룹이 있는가? ➔ 즉시 숨김
    3. 메뉴의 allow_groups 에 사용자의 부그룹/주그룹이 있는가? ➔ 랭킹 무관 노출
    4. 메뉴의 min_rank 와 사용자 랭킹 비교 ➔ 이상이면 노출
    """
    filtered = []
    sorted_menus = sorted(menus, key=lambda x: x.order)
    
    for m in sorted_menus:
        # 📌 [버그 수정]: 메뉴는 AppRegistry 객체가 아니라 개별 속성(min_rank, allow_groups, deny_groups)을
        #    직접 전달하므로 core.permission.evaluate_permission()으로 4단계 권한을 판별합니다.
        is_allowed = True if bypass_auth else (
            bool(m.is_visible) and evaluate_permission(
                user=current_user,
                action="read",
                min_read_rank=m.min_rank if m.min_rank is not None else 0,
                allow_groups=m.allow_groups or [],
                deny_groups=m.deny_groups or [],
            )
        )

        # 🚨 [앱 킬 스위치 연동]: 연결된 앱이 비활성화(is_active=False)된 경우 일반 사용자 메뉴 자동 숨김
        if is_allowed and not bypass_auth and m.app_id:
            user_rank = get_user_rank(current_user)
            if user_rank != ROOT_RANK:
                app_meta = db.query(AppRegistry.is_active).filter(AppRegistry.app_id == m.app_id).first()
                if app_meta and app_meta[0] is False:
                    is_allowed = False
        if is_allowed:
            # 동적 URL 계산 (INSTANCE / CUSTOM / SYSTEM 분류 체계 반영)
            final_url = resolve_menu_url(m, db)
            normalized_link_type = "INSTANCE" if m.link_type == "APP" else m.link_type
            
            menu_data = {
                "id": m.id, "title": m.title, "parent_id": m.parent_id,
                "icon_name": m.icon_name, "icon_color": m.icon_color,
                "link_type": normalized_link_type, "external_url": final_url,
                "order": m.order, "is_visible": m.is_visible, "min_rank": m.min_rank,
                "allow_groups": m.allow_groups or [],
                "deny_groups": m.deny_groups or [],
                "app_id": m.app_id, "app_instance_id": m.app_instance_id if bypass_auth else (get_instance_slug(m, db) or m.app_instance_id),
                "sub_menus": filter_menu_tree(m.sub_menus, current_user, db, bypass_auth=bypass_auth)
            }
            filtered.append(menu_data)
    return filtered

@router.get("/menu/public", response_model=List[admin_schema.MenuSchema])
def get_public_menus(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """일반 사용자용 공개 메뉴 조회 (4단계 그룹/랭킹 권한 필터링 및 지능형 URL 생성 포함)"""
    # 📌 SQL 단계에서 min_rank로 미리 자르지 않고(그룹 허용 예외 반영을 위해),
    #    가시성(is_visible=True)이 켜진 루트 메뉴를 모두 가져온 뒤 4단계 권한 엔진(filter_menu_tree)으로 판별합니다.
    root_menus = db.query(Menu).options(joinedload(Menu.sub_menus)).filter(
        Menu.parent_id == None, Menu.is_visible == True
    ).order_by(Menu.order).all()
    
    filtered_menus = filter_menu_tree(root_menus, current_user, db, bypass_auth=False)
    return filtered_menus

@router.get("/menu", response_model=List[admin_schema.MenuSchema])
def get_all_menus(db: Session = Depends(get_db), admin: User = Depends(check_menu_admin_read)):
    """관리자용 전체 메뉴 트리 (admin_menu 거버넌스 연동)"""
    legacy_menus = db.query(Menu).filter(Menu.link_type == "APP").all()
    if legacy_menus:
        for lm in legacy_menus:
            lm.link_type = "INSTANCE"
        db.commit()

    # SYSTEM 메뉴 또는 잘못된 admin_admin_* 주소 자가치유 보정
    broken_menus = db.query(Menu).filter(
        (Menu.link_type == "SYSTEM") | (Menu.external_url.like("%/admin/admin_%"))
    ).all()
    if broken_menus:
        for bm in broken_menus:
            bm.external_url = resolve_menu_url(bm, db)
        db.commit()

    root_menus = db.query(Menu).options(joinedload(Menu.sub_menus)).filter(Menu.parent_id == None).order_by(Menu.order).all()
    return filter_menu_tree(root_menus, admin, db, bypass_auth=True)

@router.post("/menu", response_model=admin_schema.MenuSchema)
def create_menu(menu_in: admin_schema.MenuCreate, db: Session = Depends(get_db), admin: User = Depends(check_menu_admin_write)):
    data = menu_in.dict()
    if data.get("link_type") == "APP":
        data["link_type"] = "INSTANCE"
    elif data.get("link_type") == "SYSTEM":
        data["app_instance_id"] = -1

    original_instance_id = data.get("app_instance_id")
    
    if original_instance_id and isinstance(original_instance_id, str):
        if data.get("app_id") in ["page", "pages"]:
            page_obj = db.query(Page).filter(Page.slug == original_instance_id).first()
            if page_obj:
                data["app_instance_id"] = page_obj.id
        else:
            board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
            if board:
                data["app_instance_id"] = board.id
    
    db_menu = Menu(**data)
    db.add(db_menu)
    db.commit()
    db.refresh(db_menu)

    # 링크 타입이 엔진 또는 정적 레이어 기반인 경우 정규화된 URL 동기화 저장
    if db_menu.link_type in ["INSTANCE", "CUSTOM", "SYSTEM", "APP", "PAGES", "PAGE"]:
        db_menu.external_url = resolve_menu_url(db_menu, db)
        db.commit()
        db.refresh(db_menu)

    # 📜 [시스템 및 보안 감사로그 영구 기록]
    safe_log_audit(
        db=db,
        app_id="menu",
        log_type="SYSTEM",
        action="MENU_CREATED",
        title=f"메뉴 항목 생성: {db_menu.title} (ID: {db_menu.id})",
        user=admin,
        resource_type="menu",
        resource_id=str(db_menu.id),
        message=f"타입: {db_menu.link_type}, URL: {db_menu.external_url}, 권한: R{db_menu.min_rank}",
        metadata={
            "menu_id": db_menu.id,
            "title": db_menu.title,
            "parent_id": db_menu.parent_id,
            "link_type": db_menu.link_type,
            "external_url": db_menu.external_url,
            "app_id": db_menu.app_id,
            "min_rank": db_menu.min_rank,
            "allow_groups": db_menu.allow_groups,
            "deny_groups": db_menu.deny_groups,
        }
    )
    
    # 응답 시 slug가 원래 요청에 있었다면 slug로 복구
    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id
        
    return result

@router.put("/menu/{menu_id}", response_model=admin_schema.MenuSchema)
def update_menu(menu_id: int, menu_in: admin_schema.MenuUpdate, db: Session = Depends(get_db), admin: User = Depends(check_menu_admin_write)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)
    
    data = menu_in.dict(exclude_unset=True)
    if data.get("link_type") == "APP":
        data["link_type"] = "INSTANCE"
    elif data.get("link_type") == "SYSTEM":
        data["app_instance_id"] = -1

    original_instance_id = data.get("app_instance_id")
    
    if original_instance_id and isinstance(original_instance_id, str):
        if data.get("app_id") in ["page", "pages"]:
            page_obj = db.query(Page).filter(Page.slug == original_instance_id).first()
            if page_obj:
                data["app_instance_id"] = page_obj.id
        else:
            board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
            if board:
                data["app_instance_id"] = board.id

    # 📜 변경 전/후 diff 추출
    diff_list = []
    for key, value in data.items():
        old_val = getattr(db_menu, key, None)
        if old_val != value:
            diff_list.append({
                "field": key,
                "old": old_val,
                "new": value
            })
        setattr(db_menu, key, value)

    db.commit()
    db.refresh(db_menu)

    # 링크 타입이 엔진 또는 정적 레이어 기반인 경우 정규화된 URL 동기화 저장
    if db_menu.link_type in ["INSTANCE", "CUSTOM", "SYSTEM", "APP", "PAGES", "PAGE"]:
        db_menu.external_url = resolve_menu_url(db_menu, db)
        db.commit()
        db.refresh(db_menu)

    # 📜 [시스템/보안 감사로그 영구 기록]
    if diff_list:
        is_security_change = any(
            f["field"] in ["min_rank", "allow_groups", "deny_groups", "is_visible"] 
            for f in diff_list
        )
        safe_log_audit(
            db=db,
            app_id="menu",
            log_type="SECURITY" if is_security_change else "SYSTEM",
            action="MENU_UPDATED",
            title=f"메뉴 항목 수정: {db_menu.title} (ID: {db_menu.id})",
            user=admin,
            resource_type="menu",
            resource_id=str(db_menu.id),
            message=f"{len(diff_list)}개 항목 변경 완료: " + ", ".join([d["field"] for d in diff_list]),
            diff_payload=diff_list,
            metadata={"menu_id": db_menu.id, "updated_fields": list(data.keys())}
        )
    
    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id
        
    return result

@router.delete("/menu/{menu_id}")
def delete_menu(menu_id: int, db: Session = Depends(get_db), admin: User = Depends(check_menu_admin_write)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)

    menu_id_val = db_menu.id
    menu_title = db_menu.title
    menu_url = db_menu.external_url

    db.delete(db_menu)
    db.commit()

    # 📜 [보안 감사로그 영구 기록]
    safe_log_audit(
        db=db,
        app_id="menu",
        log_type="SECURITY",
        action="MENU_DELETED",
        title=f"메뉴 항목 삭제 완료: {menu_title} (ID: {menu_id_val})",
        user=admin,
        severity="WARN",
        resource_type="menu",
        resource_id=str(menu_id_val),
        message=f"메뉴 '{menu_title}' (URL: {menu_url}) 항목이 시스템에서 영구 삭제되었습니다.",
        metadata={"menu_id": menu_id_val, "title": menu_title, "url": menu_url}
    )

    return {"message": "success"}

# --- System Configuration (admin_config 거버넌스 연동) ---

@router.get("/config", response_model=List[admin_schema.SystemConfigSchema])
def get_all_configs(db: Session = Depends(get_db), admin: User = Depends(check_config_admin_read)):
    """전사 시스템 환경 설정 조회 (config 앱 읽기 권한 이상)"""
    return db.query(SystemConfig).order_by(SystemConfig.key).all()

@router.put("/config/batch")
def update_configs_batch(
    payload: dict = Body(..., description="키-값 딕셔너리"),
    db: Session = Depends(get_db),
    admin: User = Depends(check_config_admin_write)
):
    """
    [전사 시스템 환경 설정 일괄 저장]
    단일 트랜잭션으로 여러 설정을 안전하게 원자적 저장하고, 변경 감사로그를 자동 기록합니다.
    """
    changed_diff = {}
    for key, new_val in payload.items():
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        old_val = config.value if config else None
        if not config:
            config = SystemConfig(key=key, value=new_val)
            db.add(config)
            changed_diff[key] = {"old": None, "new": new_val}
        else:
            if config.value != new_val:
                changed_diff[key] = {"old": old_val, "new": new_val}
                config.value = new_val

    if changed_diff:
        db.commit()
        # 📜 [보안 감사로그]: 시스템 환경설정 일괄 변경 자동 기록
        safe_log_audit(
            db=db,
            app_id="config",
            log_type="CHANGE",
            severity="INFO",
            action="CONFIG_BATCH_UPDATED",
            title=f"관리자({admin.username})에 의한 시스템 환경설정 {len(changed_diff)}건 일괄 변경",
            user=admin,
            resource_type="system_config",
            message=f"환경설정 항목 {list(changed_diff.keys())} 변경 완료",
            diff_payload=[{"field": k, "from": str(v["old"]), "to": str(v["new"])} for k, v in changed_diff.items()],
            metadata={"admin_id": admin.id, "changes": changed_diff}
        )

    return {"message": "success", "updated_count": len(changed_diff), "keys": list(changed_diff.keys())}

@router.put("/config/{key}", response_model=admin_schema.SystemConfigSchema)
def update_config(
    key: str,
    payload: admin_schema.SystemConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_config_admin_write)
):
    """단일 시스템 환경 설정 갱신 (하위 호환)"""
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    old_val = config.value if config else None
    if not config:
        config = SystemConfig(key=key, value=payload.value, description=payload.description)
        db.add(config)
    else:
        config.value = payload.value
        if payload.description is not None:
            config.description = payload.description
    db.commit()
    db.refresh(config)

    # 📜 [보안 감사로그]: 시스템 환경설정 단일 항목 변경 기록
    safe_log_audit(
        db=db,
        app_id="config",
        log_type="CHANGE",
        severity="INFO",
        action="CONFIG_UPDATED",
        title=f"관리자({admin.username})에 의한 환경설정 '{key}' 변경",
        user=admin,
        resource_type="system_config",
        resource_id=key,
        message=f"설정 '{key}' 값이 변경되었습니다: {old_val} -> {payload.value}",
        diff_payload=[{"field": key, "from": str(old_val), "to": str(payload.value)}],
        metadata={"admin_id": admin.id, "key": key, "old_value": old_val, "new_value": payload.value}
    )

    return config

@router.get("/config/public")
def get_public_configs(db: Session = Depends(get_db)):
    configs = db.query(SystemConfig).all()
    return {c.key: c.value for c in configs}

@router.post("/system/gc/run")
def run_manual_gc(db: Session = Depends(get_db), admin: User = Depends(check_config_admin_write)):
    """[관리자 수동 즉시 실행] 데이터 보존 기간 초과 이력 및 Redis 메모리 가비지 컬렉션(GC) (STD-SYS-009)"""
    from redis_config import rd
    from domain.system.retention_service import run_data_retention_gc
    gc_result = run_data_retention_gc(db, rd)

    # 📜 [보안 감사로그]: 수동 GC 실행 기록
    safe_log_audit(
        db=db,
        app_id="config",
        log_type="SECURITY",
        severity="WARN",
        action="MANUAL_GC_TRIGGERED",
        title=f"관리자({admin.username})에 의한 전사 수동 가비지 컬렉션(GC) 즉시 실행",
        user=admin,
        resource_type="system_gc",
        message=(
            f"수동 GC 완료: 태스크 {gc_result.get('deleted_tasks', 0)}건, "
            f"세션 {gc_result.get('deleted_sessions', 0)}건, "
            f"감사로그 {gc_result.get('deleted_audit_logs', 0)}건 정리, "
            f"Redis TTL {gc_result.get('redis_ttl_enforced', 0)}건 주입, "
            f"고아키 {gc_result.get('redis_orphans_removed', 0)}건 수거"
        ),
        metadata={"admin_id": admin.id, "gc_result": gc_result}
    )

    return gc_result

# --- Board Configuration Management (게시판 설정 관리) ---

@router.get("/boards", response_model=List[admin_schema.BoardConfigAdminSchema])
def get_all_boards(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(BoardConfig).order_by(BoardConfig.id).all()

@router.post("/boards", response_model=admin_schema.BoardConfigAdminSchema)
def create_board_config(board_in: admin_schema.BoardConfigCreate, db: Session = Depends(get_db), admin: User = Depends(check_board_admin_write)):
    if db.query(BoardConfig).filter(BoardConfig.slug == board_in.slug).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    db_board = BoardConfig(**board_in.dict())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.put("/boards/{board_id}", response_model=admin_schema.BoardConfigAdminSchema)
def update_board_config(board_id: int, board_in: admin_schema.BoardConfigUpdate, db: Session = Depends(get_db), admin: User = Depends(check_board_admin_write)):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    for key, value in board_in.dict(exclude_unset=True).items():
        setattr(db_board, key, value)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.delete("/boards/{board_id}")
def delete_board_config(board_id: int, db: Session = Depends(get_db), admin: User = Depends(check_board_admin_write)):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    db.delete(db_board)
    db.commit()
    return {"message": "success"}

# --- Selection Lists ---

@router.get("/boards/list", response_model=List[admin_schema.BoardSimpleSchema])
def list_boards_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(BoardConfig).filter(BoardConfig.is_active == True).order_by(BoardConfig.name).all()

@router.get("/posts/list", response_model=List[admin_schema.PostSimpleAdminSchema])
def list_posts_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(Post).order_by(Post.create_date.desc()).limit(100).all()

from domain.push.push_service import send_push_to_all

# --- Push Notification Management (푸시 알림 관리) ---

@router.get("/push/subscriptions")
def list_push_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin)
):
    """모든 푸시 구독 목록 조회 (관리자용 - 기기/브라우저 유형 및 소속 그룹 상세 포함)"""
    subs = db.query(models.PushSubscription).join(models.User, models.PushSubscription.user_id == models.User.id).all()
    result = []
    for s in subs:
        user = db.query(models.User).filter(models.User.id == s.user_id).first()
        profile = user.profile if user else None

        # 🌐 엔드포인트 도메인 기반 기기 및 브라우저 플랫폼 판별
        ep_lower = (s.endpoint or "").lower()
        if "fcm.googleapis.com" in ep_lower or "google" in ep_lower:
            browser_type = "Chrome / Android"
            browser_icon = "mdi:google-chrome"
            badge_color = "bg-blue-50 text-blue-700 border-blue-200"
        elif "mozilla" in ep_lower or "firefox" in ep_lower:
            browser_type = "Firefox"
            browser_icon = "mdi:firefox"
            badge_color = "bg-amber-50 text-amber-700 border-amber-200"
        elif "apple" in ep_lower or "safari" in ep_lower:
            browser_type = "Safari / iOS"
            browser_icon = "mdi:apple-safari"
            badge_color = "bg-purple-50 text-purple-700 border-purple-200"
        elif "microsoft" in ep_lower or "edge" in ep_lower:
            browser_type = "Microsoft Edge"
            browser_icon = "mdi:microsoft-edge"
            badge_color = "bg-cyan-50 text-cyan-700 border-cyan-200"
        else:
            browser_type = "Web Push Standard"
            browser_icon = "mdi:cellphone-wireless"
            badge_color = "bg-slate-50 text-slate-700 border-slate-200"

        result.append({
            "id": s.id,
            "user_id": s.user_id,
            "username": user.username if user else "Unknown",
            "real_name": (user.real_name if user and user.real_name else "") or (user.username if user else ""),
            "primary_group": profile.primary_group if profile and profile.primary_group else "소속 미정",
            "rank_level": profile.rank_level if profile else 0,
            "endpoint": s.endpoint,
            "endpoint_preview": s.endpoint[:75] + "..." if len(s.endpoint) > 75 else s.endpoint,
            "browser_type": browser_type,
            "browser_icon": browser_icon,
            "badge_color": badge_color,
        })
    return result

@router.post("/push/send")
def admin_send_push(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write)
):
    """관리자가 커스텀 메시지를 전체 푸시 발송"""
    title = payload.get("title", "공지사항")
    body = payload.get("body", "")
    
    if not body:
        raise HTTPException(status_code=400, detail="메시지 본문을 입력해주세요.")
        
    # 기존에 만들어둔 발송 함수 활용 (전체 발송)
    from domain.push.push_service import send_push_to_all
    result = send_push_to_all(title, body, db=db)
    
    return {"message": "success", "sent_count": result.get("sent", 0)}

@router.delete("/push/subscriptions")
def delete_all_push_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write)
):
    """전체 푸시 구독 기기 목록 일괄 초기화(전체 삭제)"""
    deleted_count = db.query(models.PushSubscription).delete(synchronize_session=False)
    db.commit()
    return {"message": "success", "deleted_count": deleted_count}

@router.delete("/push/subscriptions/{sub_id}")
def delete_push_subscription(
    sub_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write)
):
    """무효한 푸시 구독 정보 강제 삭제"""
    sub = db.query(models.PushSubscription).filter(models.PushSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    db.delete(sub)
    db.commit()
    return {"message": "success"}

# --- DayOff Management (전체 휴무 관리) ---

@router.get("/dayoffs")
def admin_get_all_dayoffs(db: Session = Depends(get_db), admin: User = Depends(check_dayoff_admin)):
    """모든 사용자의 휴무 신청 내역 조회 (관리자용 - 원본 데이터)"""
    dayoffs = db.query(DayOff).join(User).filter(DayOff.is_deleted == False).order_by(DayOff.date.desc()).all()
    
    result = []
    for d in dayoffs:
        result.append({
            "id": d.id,
            "user_id": d.user_id,
            "username": d.user.username,
            "real_name": d.user.real_name,
            "date": str(d.date),
            "type": d.type,
            "status": d.status,
            "memo": d.memo,
            "group_id": d.group_id,
            "create_date": d.create_date
        })
    return result

@router.put("/dayoffs/{dayoff_id}/status")
def admin_update_dayoff_status(
    dayoff_id: int, 
    status_update: dict = Body(...), 
    db: Session = Depends(get_db), 
    admin: User = Depends(check_dayoff_admin_write)
):
    """휴무 신청 상태 변경 (승인/반려 등)"""
    new_status = status_update.get("status")
    db_dayoff = db.query(DayOff).filter(DayOff.id == dayoff_id).first()
    if not db_dayoff:
        raise HTTPException(status_code=404, detail="내역을 찾을 수 없습니다.")
    
    # 그룹 전체 상태 동기화
    if db_dayoff.group_id:
        items = db.query(DayOff).filter(DayOff.group_id == db_dayoff.group_id).all()
        for item in items:
            item.status = new_status
    else:
        db_dayoff.status = new_status
        
    db.commit()
    return {"message": "success", "new_status": new_status}

# --- [v1.6] Service App Architecture 관리 API ---

# 1. Service Registry (대분류)
@router.get("/service-registries", response_model=List[admin_schema.ServiceRegistrySchema])
def list_service_registries(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceRegistry).all()

@router.post("/service-registries", response_model=admin_schema.ServiceRegistrySchema)
def create_service_registry(data: admin_schema.ServiceRegistryCreate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = ServiceRegistry(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-registries/{registry_id}")
def delete_service_registry(registry_id: str, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = db.query(ServiceRegistry).filter(ServiceRegistry.id == registry_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}

# 2. Service Engine (컴포넌트 버전)
@router.get("/service-engines", response_model=List[admin_schema.ServiceEngineSchema])
def list_service_engines(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceEngine).all()

@router.post("/service-engines", response_model=admin_schema.ServiceEngineSchema)
def create_service_engine(data: admin_schema.ServiceEngineCreate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = ServiceEngine(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-engines/{engine_id}")
def delete_service_engine(engine_id: str, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = db.query(ServiceEngine).filter(ServiceEngine.id == engine_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}

# 3. Service App (원자적 인스턴스)
@router.get("/service-apps", response_model=List[admin_schema.ServiceAppSchema])
def list_service_apps(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceApp).all()

@router.post("/service-apps", response_model=admin_schema.ServiceAppSchema)
def create_service_app(data: admin_schema.ServiceAppCreate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = ServiceApp(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.put("/service-apps/{app_id}", response_model=admin_schema.ServiceAppSchema)
def update_service_app(app_id: int, data: admin_schema.ServiceAppUpdate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# 4. Service Instance (번들)
@router.get("/service-instances", response_model=List[admin_schema.ServiceInstanceSchema])
def list_service_instances(db: Session = Depends(get_db), admin: User = Depends(check_service_admin)):
    return db.query(ServiceInstance).all()

@router.post("/service-instances", response_model=admin_schema.ServiceInstanceSchema)
def create_service_instance(data: admin_schema.ServiceInstanceCreate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = ServiceInstance(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.put("/service-instances/{instance_id}", response_model=admin_schema.ServiceInstanceSchema)
def update_service_instance(instance_id: int, data: admin_schema.ServiceInstanceUpdate, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-instances/{instance_id}")
def delete_service_instance(instance_id: int, db: Session = Depends(get_db), admin: User = Depends(check_service_admin_write)):
    db_obj = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}


# =====================================================================
# 🚐 [v3.0.0] 노선 마스터 및 시간표 연동 API (Route Master & Timetables)
# =====================================================================

@router.get("/route-masters")
def list_route_masters(
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin)
):
    """
    모든 노선 마스터 및 이에 소속된 버전별 시간표 상세 정보를 조회합니다.
    - 정규노선(REGULAR) / 임시노선(TEMPORARY)을 완벽히 수용하여 반환합니다.
    """
    try:
        # RouteMaster 및 연동된 timetables 테이블을 효율적으로 조인 로딩(joinedload)하여 쿼리
        masters = db.query(RouteMaster).options(
            joinedload(RouteMaster.timetables)
        ).order_by(
            RouteMaster.route_name.asc(), 
            RouteMaster.version.asc()
        ).all()
        
        result = []
        for m in masters:
            # 시간표는 seq(순번) 오름차순으로 정렬하여 반환
            sorted_timetables = sorted(m.timetables, key=lambda x: x.seq)
            
            result.append({
                "id": m.id,
                "route_name": m.route_name,
                "route_type": m.route_type,
                "start_date": str(m.start_date),
                "end_date": str(m.end_date) if m.end_date else None,
                "vehicle_count": m.vehicle_count,
                "version": m.version,
                "is_regular_duty": m.is_regular_duty,
                "timetables": [
                    {
                        "id": t.id,
                        "route_master_id": t.route_master_id,
                        "route_name": t.route_name,
                        "seq": t.seq,
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                        "start_location": t.start_location,
                        "end_location": t.end_location,
                        "version": t.version,
                        "start_garage": t.start_garage,
                        "end_garage": t.end_garage,
                        "is_regular_duty": t.is_regular_duty
                    } for t in sorted_timetables
                ]
            })
        return result
    except Exception as e:
        print(f"❌ [AdminRouteMaster] Error listing route masters: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 조회하는 중 서버 오류가 발생하였습니다.")


@router.post("/route-masters")
def create_route_master(
    payload: admin_schema.RouteMasterCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write)
):
    """
    새로운 노선 마스터 및 관련 상세 시간표를 일괄적으로 등록합니다.
    - 트랜잭션을 적용하여 시간표 등록 중 하나라도 실패할 시 전체 롤백 처리합니다.
    """
    try:
        # 1. RouteMaster DB 레코드 생성
        db_master = RouteMaster(
            route_name=payload.route_name,
            route_type=payload.route_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            vehicle_count=payload.vehicle_count,
            version=payload.version,
            is_regular_duty=payload.is_regular_duty
        )
        db.add(db_master)
        db.flush()  # timetable_id 바인딩을 위한 고유 ID 선점 획득
        
        # 2. 입력받은 시간표 상세 명세 등록
        for t in payload.timetables:
            db_timetable = RouteTimetable(
                route_master_id=db_master.id,
                route_name=payload.route_name,
                seq=t.seq,
                start_time=t.start_time,
                end_time=t.end_time,
                start_location=t.start_location,
                end_location=t.end_location,
                version=payload.version,
                start_garage=t.start_garage,
                end_garage=t.end_garage,
                is_regular_duty=t.is_regular_duty
            )
            db.add(db_timetable)
            
        db.commit()
        db.refresh(db_master)
        return {"message": "success", "id": db_master.id}
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error creating route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 생성하는 중 오류가 발생하였습니다.")


@router.put("/route-masters/{master_id}")
def update_route_master(
    master_id: int,
    payload: admin_schema.RouteMasterUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write)
):
    """
    노선 마스터 및 관련 상세 시간표를 일괄적으로 수정(오버라이트)합니다.
    - 특정 텍스트 필드 혹은 날짜만 선택적으로 변경 가능합니다.
    - timetables 필드가 전달되면 기존 시간표를 모두 지우고 일괄 재생성합니다.
    """
    try:
        db_master = db.query(RouteMaster).filter(RouteMaster.id == master_id).first()
        if not db_master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")
            
        # 1. 노선 마스터 기본 필드 업데이트
        if payload.route_name is not None:
            db_master.route_name = payload.route_name
        if payload.route_type is not None:
            db_master.route_type = payload.route_type
        if payload.start_date is not None:
            db_master.start_date = payload.start_date
        if payload.end_date is not None:
            db_master.end_date = payload.end_date
        if payload.vehicle_count is not None:
            db_master.vehicle_count = payload.vehicle_count
        if payload.version is not None:
            db_master.version = payload.version
        if payload.is_regular_duty is not None:
            db_master.is_regular_duty = payload.is_regular_duty
            
        # 2. 시간표 리스트가 명시적으로 들어왔을 때 기존 상세 회차 시간표 덮어쓰기 수행
        if payload.timetables is not None:
            # 해당 노선 마스터 ID를 가리키는 기존 시간표 레코드 전체 삭제
            db.query(RouteTimetable).filter(RouteTimetable.route_master_id == master_id).delete()
            
            # 신규 시간표 일괄 생성
            for t in payload.timetables:
                db_timetable = RouteTimetable(
                    route_master_id=db_master.id,
                    route_name=db_master.route_name,
                    seq=t.seq,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    start_location=t.start_location,
                    end_location=t.end_location,
                    version=db_master.version,
                    start_garage=t.start_garage,
                    end_garage=t.end_garage,
                    is_regular_duty=t.is_regular_duty
                )
                db.add(db_timetable)
                
        db.commit()
        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error updating route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 수정하는 중 오류가 발생하였습니다.")


@router.delete("/route-masters/{master_id}")
def delete_route_master(
    master_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write)
):
    """
    특정 노선 마스터와 종속된 모든 상세 시간표를 물리적으로 영구 삭제합니다.
    """
    try:
        db_master = db.query(RouteMaster).filter(RouteMaster.id == master_id).first()
        if not db_master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")
            
        db.delete(db_master)
        db.commit()
        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error deleting route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 삭제하는 중 오류가 발생하였습니다.")


# =====================================================================
# 🚐 [v3.0.0] 일일 배차 관리 API (Dispatch Management)
# =====================================================================

import json
import os
from datetime import timedelta

def load_drivers_metadata():
    """
    Svelte 프론트엔드의 drivers.json 파일을 읽어서 기사 메타데이터를 구조화합니다.
    """
    try:
        path = "/home/lee/uv-code/svelte5/src/lib/data/drivers.json"
        if os.path.exists(path):
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
    """
    Svelte 프론트엔드의 vehicles.json 파일을 읽어서 노선별 차량 풀을 가져옵니다.
    """
    try:
        path = "/home/lee/uv-code/svelte5/src/lib/data/vehicles.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("vehicles", {})
        return {}
    except Exception as e:
        print(f"⚠️ [load_vehicles_metadata] Error: {e}")
        return {}


@router.get("/dispatch/active-routes", response_model=List[dict])
def list_active_routes_for_date(
    target_date: date,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin)
):
    """
    지정된 날짜(target_date) 기준으로 운행(활성) 중인 노선 마스터 목록을 조회합니다.
    """
    try:
        # start_date <= target_date <= end_date (or end_date is null)
        masters = db.query(RouteMaster).filter(
            RouteMaster.start_date <= target_date,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= target_date)
        ).order_by(RouteMaster.route_name.asc()).all()

        return [
            {
                "id": m.id,
                "route_name": m.route_name,
                "route_type": m.route_type,
                "start_date": str(m.start_date),
                "end_date": str(m.end_date) if m.end_date else None,
                "vehicle_count": m.vehicle_count,
                "version": m.version,
                "is_regular_duty": m.is_regular_duty
            }
            for m in masters
        ]
    except Exception as e:
        print(f"❌ [AdminDispatch] Error listing active routes: {e}")
        raise HTTPException(status_code=500, detail="활성 노선 정보를 조회하는 중 오류가 발생하였습니다.")


@router.get("/dispatch", response_model=List[admin_schema.DispatchRowResponse])
def get_daily_dispatch(
    target_date: date,
    route_master_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin)
):
    """
    지정된 날짜와 노선 마스터 ID에 해당하는 배차 목록을 조회합니다.
    - 당연근무일 경우 전날 실제 기사 승계 추천
    - 그 외의 미저장 칸은 빈 칸("") 처리
    - "어제 실제 운행했던 기사 이름(yesterday_driver_name)"을 반환하여 프론트엔드 자동 채우기 연산 지원
    """
    try:
        master = db.query(RouteMaster).filter(RouteMaster.id == route_master_id).first()
        if not master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")

        timetables = db.query(RouteTimetable).filter(
            RouteTimetable.route_master_id == route_master_id
        ).order_by(RouteTimetable.seq.asc()).all()

        if not timetables:
            return []

        N = len(timetables)

        delta_days = (target_date - master.start_date).days
        if delta_days < 0:
            delta_days = 0

        # 드라이버 & 차량 메타데이터 로드
        role_map, vehicle_map, vehicle_drivers = load_drivers_metadata()
        vehicles_dict = load_vehicles_metadata()

        # 노선별 기본 전담차량 풀 구성
        route_name = master.route_name or ""
        target_fleet = []
        if "121" in route_name or "122" in route_name:
            target_fleet = vehicles_dict.get("121/122", [])
        elif "291" in route_name or "292" in route_name or "293" in route_name:
            target_fleet = vehicles_dict.get("291/292/293", [])
        else:
            target_fleet = vehicles_dict.get("121/122", []) + vehicles_dict.get("291/292/293", [])

        # 대상 시간표 ID 필터로 금일 배차 맵 구하기
        timetable_ids = [t.id for t in timetables]
        existing_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == target_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        dispatch_map = {d.timetable_id: d for d in existing_dispatches}

        # 내일 날짜 산출 및 배차 맵 구하기
        tomorrow_date = target_date + timedelta(days=1)
        tomorrow_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == tomorrow_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        tomorrow_map = {td.timetable_id: td for td in tomorrow_dispatches}

        # 어제 날짜 산출 및 배차 맵 구하기 (어제 실제 운행 기사 조회용)
        yesterday_date = target_date - timedelta(days=1)
        yesterday_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == yesterday_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        yesterday_map = {yd.timetable_id: yd for yd in yesterday_dispatches}

        # 1단계: 오늘 각 물리적 행에 대응하는 기사 정보 pre-calculation (동일 물리적 행에서의 승계 처리)
        today_drivers = []
        for i, t in enumerate(timetables):
            shifted_index = (i + delta_days) % N
            ref_t = timetables[shifted_index]

            # 어제(전일) 이 물리적 행에 대응되었던 시간표의 당연근무 여부 산출
            yesterday_shifted_index = (i + delta_days - 1) % N
            ref_t_yesterday = timetables[yesterday_shifted_index]
            is_yesterday_regular_duty = ref_t_yesterday.is_regular_duty

            # 당연근무 여부와 관계없이, 주기사/보조기사의 물리적 행(t.id)은 고정이므로 어제 동일 행의 배차 조회
            yesterday_disp = yesterday_map.get(t.id)
            yesterday_driver_name = yesterday_disp.driver_name if (yesterday_disp and yesterday_disp.driver_name) else None

            d = dispatch_map.get(t.id)
            driver_name = ""
            is_inherited = False

            if d is not None:
                driver_name = d.driver_name or ""
                is_inherited = False
            else:
                # 오늘 배차 레코드가 없는 경우, 어제 당연근무(1로번)에 해당했다면 어제 동일 행의 기사명을 상속 (연속 근무)
                if is_yesterday_regular_duty:
                    if yesterday_driver_name:
                        driver_name = yesterday_driver_name
                        is_inherited = True

            today_drivers.append({
                "driver_name": driver_name,
                "is_inherited": is_inherited,
                "yesterday_driver_name": yesterday_driver_name,
                "is_yesterday_regular_duty": is_yesterday_regular_duty
            })

        # 2단계: 내일 당연근무를 수행할 기사 예측을 포함한 최종 결과 목록 구성
        result = []
        for i, t in enumerate(timetables):
            shifted_index = (i + delta_days) % N
            ref_t = timetables[shifted_index]

            # 내일 날짜의 shifted_index 및 당연근무 여부 산출
            tomorrow_shifted_index = (i + delta_days + 1) % N
            ref_t_tomorrow = timetables[tomorrow_shifted_index]
            is_tomorrow_regular_duty = ref_t_tomorrow.is_regular_duty

            default_vehicle = target_fleet[i] if i < len(target_fleet) else ""

            today_info = today_drivers[i]
            driver_name = today_info["driver_name"]
            is_inherited = today_info["is_inherited"]
            yesterday_driver_name = today_info["yesterday_driver_name"]

            d = dispatch_map.get(t.id)
            vehicle_no = default_vehicle
            if d and d.vehicle_no:
                vehicle_no = d.vehicle_no

            # 3. 내일 날짜 기사 및 상속 여부 결정
            td_d = tomorrow_map.get(t.id)
            tomorrow_driver_name = ""
            is_tomorrow_inherited = False

            if td_d and td_d.driver_name and td_d.driver_name.strip():
                tomorrow_driver_name = td_d.driver_name
                is_tomorrow_inherited = False
            else:
                # 오늘 당연근무(1로번)인 경우: 오늘과 내일 연속 근무이므로 교대 로테이션 없이 오늘 기사를 내일 기사로 그대로 유지
                if ref_t.is_regular_duty:
                    if driver_name and driver_name.strip():
                        tomorrow_driver_name = driver_name
                        is_tomorrow_inherited = True
                else:
                    # 일반 로테이션 추천은 프론트엔드에서 수동/자동으로만 관리하므로 백엔드는 예측 공란 처리
                    tomorrow_driver_name = ""
                    is_tomorrow_inherited = False

            result.append({
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
                "is_yesterday_regular_duty": today_info["is_yesterday_regular_duty"],
                "is_inherited": is_inherited,
                "is_tomorrow_inherited": is_tomorrow_inherited
            })

        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [AdminDispatch] Error fetching dispatch data with rotation: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 조회하는 중 오류가 발생하였습니다.")


@router.post("/dispatch")
def save_daily_dispatch(
    payload: admin_schema.DispatchSavePayload,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin_write)
):
    """
    일괄 배차 정보(금일 및 익일)를 생성하거나 업데이트(Upsert) 합니다.
    - 단일 트랜잭션으로 오늘과 내일의 배차 현황을 안전하게 교차 일괄 영구 저장합니다.
    """
    try:
        role_map, vehicle_map, _ = load_drivers_metadata()
        
        for r in payload.rows:
            # 1. 오늘 날짜 배차 데이터 Upsert
            db_dispatch = db.query(models.Dispatch).filter(
                models.Dispatch.target_date == payload.target_date,
                models.Dispatch.timetable_id == r.timetable_id
            ).first()

            if db_dispatch:
                db_dispatch.driver_name = r.driver_name
                db_dispatch.vehicle_no = r.vehicle_no
                db_dispatch.start_time = r.start_time
                db_dispatch.status = payload.status
                db_dispatch.memo = r.memo
            else:
                db_dispatch = models.Dispatch(
                    target_date=payload.target_date,
                    timetable_id=r.timetable_id,
                    driver_name=r.driver_name,
                    vehicle_no=r.vehicle_no,
                    start_time=r.start_time,
                    status=payload.status,
                    memo=r.memo
                )
                db.add(db_dispatch)

            # 2. 내일 날짜 배차 데이터 Upsert (임시 저장 및 확정 공지 모두 내일 배차 정보를 동기화)
            tomorrow_date = payload.target_date + timedelta(days=1)
            db_dispatch_tomorrow = db.query(models.Dispatch).filter(
                models.Dispatch.target_date == tomorrow_date,
                models.Dispatch.timetable_id == r.timetable_id
            ).first()

            if r.tomorrow_driver_name and r.tomorrow_driver_name.strip():
                tomorrow_driver = r.tomorrow_driver_name.strip()
                
                # 내일에 배정될 차량 번호 연동 로직
                tomorrow_vehicle = None
                if tomorrow_driver == r.driver_name:
                    tomorrow_vehicle = r.vehicle_no
                else:
                    tomorrow_vehicle = vehicle_map.get(tomorrow_driver)

                if db_dispatch_tomorrow:
                    db_dispatch_tomorrow.driver_name = tomorrow_driver
                    if not db_dispatch_tomorrow.vehicle_no or db_dispatch_tomorrow.vehicle_no.strip() == "" or tomorrow_driver != r.driver_name:
                        if tomorrow_vehicle:
                            db_dispatch_tomorrow.vehicle_no = tomorrow_vehicle
                    db_dispatch_tomorrow.status = payload.status
                else:
                    db_dispatch_tomorrow = models.Dispatch(
                        target_date=tomorrow_date,
                        timetable_id=r.timetable_id,
                        driver_name=tomorrow_driver,
                        vehicle_no=tomorrow_vehicle or r.vehicle_no,
                        status=payload.status,
                        memo=""
                    )
                    db.add(db_dispatch_tomorrow)
            else:
                # 사용자가 내일 기사를 빈 칸(null 또는 공백)으로 지정하여 저장한 경우
                # 데이터베이스에 이미 내일 데이터가 존재한다면 기사명을 빈 값(None)으로 덮어써서 비웁니다.
                if db_dispatch_tomorrow:
                    db_dispatch_tomorrow.driver_name = None
                    db_dispatch_tomorrow.status = payload.status

        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminDispatch] Error saving dispatch data: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 저장하는 중 오류가 발생하였습니다.")



