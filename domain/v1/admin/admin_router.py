from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import User, UserProfile, BoardConfig, Post, Menu, SystemConfig, AppRegistry, DayOff, ServiceRegistry, ServiceEngine, ServiceApp, ServiceInstance, RouteMaster, RouteTimetable
from domain.user.user_router import get_current_user, get_current_user_optional, RankChecker, check_rank
from domain.v1.admin import admin_schema
from typing import List, Optional, Any
from datetime import date
import re
import models

router = APIRouter(
    prefix="/admin",
    tags=["admin_v1"]
)

API_VERSION_PREFIX = "/v1"

# 편리한 최고 관리자 체크 의존성 (Rank 4 기준)
check_admin = check_rank(required_rank=4)

@router.get("/dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """관리자 대시보드 요약 정보"""
    user_count = db.query(User).count()
    board_count = db.query(BoardConfig).count()
    post_count = db.query(Post).count()
    app_count = db.query(AppRegistry).count()
    
    return {
        "user_count": user_count,
        "board_count": board_count,
        "post_count": post_count,
        "app_count": app_count,
        "admin_name": admin.real_name or admin.username
    }

# --- User Management (유저 관리) ---

@router.get("/users", response_model=List[admin_schema.UserAdminSchema])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """전체 유저 목록 조회 (관리자용)"""
    return db.query(User).options(joinedload(User.profile)).all()

@router.get("/users/{user_id}", response_model=admin_schema.UserAdminSchema)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
):
    """유저의 Rank 등급 및 승인 상태 수정"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    
    if not user.profile:
        user.profile = UserProfile(user_id=user.id)
        db.add(user.profile)
    
    user.profile.rank_level = rank_in.rank_level
    db.commit()
    return {"message": "success", "username": user.username, "new_rank": rank_in.rank_level}

# --- [v1.5] App Registry 관리 API (시스템 확장성 핵심) ---

@router.get("/apps", response_model=List[admin_schema.AppRegistrySchema])
def get_all_apps(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """시스템에 등록된 모든 App 엔진 목록 조회 (관리자용)"""
    return db.query(AppRegistry).order_by(AppRegistry.app_id).all()

@router.get("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def get_app_detail(app_id: str, db: Session = Depends(get_db)):
    """특정 앱의 메타데이터 및 설정 스키마 조회 (전체 공개 가능 - 권한 점검 시 사용)"""
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="등록되지 않은 앱 엔진입니다.")
    return db_app

@router.post("/apps", response_model=admin_schema.AppRegistrySchema)
def create_app_registry(
    app_in: admin_schema.AppRegistryCreate, 
    db: Session = Depends(get_db), 
    admin: User = Depends(check_admin)
):
    """신규 App 엔진 및 메타데이터 등록"""
    # 중복 ID 체크
    existing = db.query(AppRegistry).filter(AppRegistry.app_id == app_in.app_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 앱 식별자입니다.")
    
    db_app = AppRegistry(**app_in.dict())
    db.add(db_app)
    db.commit()
    db.refresh(db_app)
    return db_app

@router.patch("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def update_app_registry(
    app_id: str, 
    app_in: admin_schema.AppRegistryUpdate, 
    db: Session = Depends(get_db), 
    admin: User = Depends(check_admin)
):
    """App 엔진 메타데이터 수정 (권한, 경로, 관리자 권한 위임 등)"""
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    
    # 전달된 필드만 부분 업데이트 (exclude_unset=True)
    update_data = app_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_app, key, value)
    
    db.commit()
    db.refresh(db_app)
    return db_app

@router.delete("/apps/{app_id}")
def delete_app(app_id: str, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """앱 등록 제거"""
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    db.delete(db_app)
    db.commit()
    return {"message": "success"}

# --- Menu Management (지능형 메뉴 관리) ---

def resolve_menu_url(menu: Menu, db: Session) -> str:
    """[v2.2 최종] APP(표준)과 CUSTOM(커스텀) 분기형 주소 조립기"""
    # 🔗 [URL 레이어] 오직 URL 타입만 수동 입력 주소 사용
    if menu.link_type == "URL":
        return menu.external_url or "#"

    if menu.link_type in ["FOLDER", "DIVIDER"]:
        return "#"
        
    # ⚙️ [엔진 기반 레이어] APP 또는 CUSTOM
    if (menu.link_type in ["APP", "CUSTOM"]) and menu.app_id:
        instance_id = str(menu.app_instance_id) if menu.app_instance_id is not None else ""
        
        # 관리자 여부 판별 (-1)
        if instance_id == "-1":
            return f"{API_VERSION_PREFIX}/admin/{menu.app_id}"
            
        # [v2.2 최종] link_type에 따른 프리픽스 분기
        # APP -> /v1/app, CUSTOM -> /v1/custom
        prefix = f"{API_VERSION_PREFIX}/custom" if menu.link_type == "CUSTOM" else f"{API_VERSION_PREFIX}/app"

        if instance_id and instance_id != "":
            return f"{prefix}/{menu.app_id}/{instance_id}"
            
        return f"{prefix}/{menu.app_id}"

    # 📄 [PAGE 레이어]
    if menu.link_type == "PAGE" and menu.page_id:
        return f"{API_VERSION_PREFIX}/pages/{menu.page_id}"

    return menu.external_url or "#"

def get_instance_slug(menu: Menu, db: Session) -> Optional[str]:
    # app_id가 'board'인 경우 BoardConfig에서 slug를 조회
    if menu.app_id == 'board' and menu.app_instance_id:
        board = db.query(BoardConfig).filter(BoardConfig.id == menu.app_instance_id).first()
        return board.slug if board else str(menu.app_instance_id)
    return str(menu.app_instance_id) if menu.app_instance_id is not None else None

def filter_menu_tree(menus: List[Menu], user_rank: int, db: Session):
    """재귀적 메뉴 필터링 및 동적 URL 주입 + Slug 변환 적용"""
    filtered = []
    # 정렬 추가: 하위 메뉴들이 'order' 필드 기준으로 정렬되도록 보장
    sorted_menus = sorted(menus, key=lambda x: x.order)
    
    for m in sorted_menus:
        if m.is_visible and m.min_rank <= user_rank:
            # 동적 URL 계산
            final_url = resolve_menu_url(m, db)
            
            menu_data = {
                "id": m.id, "title": m.title, "parent_id": m.parent_id,
                "icon_name": m.icon_name, "icon_color": m.icon_color,
                "link_type": m.link_type, "external_url": final_url,
                "order": m.order, "is_visible": m.is_visible, "min_rank": m.min_rank,
                "app_id": m.app_id, "app_instance_id": get_instance_slug(m, db),
                "sub_menus": filter_menu_tree(m.sub_menus, user_rank, db)
            }
            filtered.append(menu_data)
    return filtered

@router.get("/menu/public", response_model=List[admin_schema.MenuSchema])
def get_public_menus(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """일반 사용자용 공개 메뉴 조회 (지능형 URL 생성 포함)"""
    user_rank = 0
    if current_user:
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    
    root_menus = db.query(Menu).options(joinedload(Menu.sub_menus)).filter(
        Menu.parent_id == None, Menu.is_visible == True, Menu.min_rank <= user_rank
    ).order_by(Menu.order).all()
    
    filtered_menus = filter_menu_tree(root_menus, user_rank, db)
    return filtered_menus

@router.get("/menu", response_model=List[admin_schema.MenuSchema])
def get_all_menus(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """관리자용 전체 메뉴 트리 (Slug 변환 포함)"""
    root_menus = db.query(Menu).options(joinedload(Menu.sub_menus)).filter(Menu.parent_id == None).order_by(Menu.order).all()
    return filter_menu_tree(root_menus, 999, db)

@router.post("/menu", response_model=admin_schema.MenuSchema)
def create_menu(menu_in: admin_schema.MenuCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    data = menu_in.dict()
    original_instance_id = data.get("app_instance_id")
    
    if original_instance_id and isinstance(original_instance_id, str):
        board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
        if board:
            data["app_instance_id"] = board.id
    
    db_menu = Menu(**data)
    db.add(db_menu)
    db.commit()
    db.refresh(db_menu)
    
    # 응답 시 slug가 원래 요청에 있었다면 slug로 복구
    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id
        
    return result

@router.put("/menu/{menu_id}", response_model=admin_schema.MenuSchema)
def update_menu(menu_id: int, menu_in: admin_schema.MenuUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)
    
    data = menu_in.dict(exclude_unset=True)
    original_instance_id = data.get("app_instance_id")
    
    if original_instance_id and isinstance(original_instance_id, str):
        board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
        if board:
            data["app_instance_id"] = board.id
    
    for key, value in data.items():
        setattr(db_menu, key, value)
    db.commit()
    db.refresh(db_menu)
    
    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id
        
    return result

@router.delete("/menu/{menu_id}")
def delete_menu(menu_id: int, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)
    db.delete(db_menu)
    db.commit()
    return {"message": "success"}

# --- System Configuration ---

@router.get("/config", response_model=List[admin_schema.SystemConfigSchema])
def get_all_configs(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(SystemConfig).all()

@router.put("/config/{key}", response_model=admin_schema.SystemConfigSchema)
def update_config(key: str, payload: admin_schema.SystemConfigUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        config = SystemConfig(key=key, value=payload.value, description=payload.description)
        db.add(config)
    else:
        config.value = payload.value
        if payload.description is not None:
            config.description = payload.description
    db.commit()
    db.refresh(config)
    return config

@router.get("/config/public")
def get_public_configs(db: Session = Depends(get_db)):
    configs = db.query(SystemConfig).all()
    return {c.key: c.value for c in configs}

# --- Board Configuration Management (게시판 설정 관리) ---

@router.get("/boards", response_model=List[admin_schema.BoardConfigAdminSchema])
def get_all_boards(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(BoardConfig).order_by(BoardConfig.id).all()

@router.post("/boards", response_model=admin_schema.BoardConfigAdminSchema)
def create_board_config(board_in: admin_schema.BoardConfigCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    if db.query(BoardConfig).filter(BoardConfig.slug == board_in.slug).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    db_board = BoardConfig(**board_in.dict())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.put("/boards/{board_id}", response_model=admin_schema.BoardConfigAdminSchema)
def update_board_config(board_id: int, board_in: admin_schema.BoardConfigUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    for key, value in board_in.dict(exclude_unset=True).items():
        setattr(db_board, key, value)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.delete("/boards/{board_id}")
def delete_board_config(board_id: int, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    db.delete(db_board)
    db.commit()
    return {"message": "success"}

# --- Selection Lists ---

@router.get("/boards/list", response_model=List[admin_schema.BoardSimpleSchema])
def list_boards_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(BoardConfig).filter(BoardConfig.is_active == True).order_by(BoardConfig.name).all()

@router.get("/posts/list", response_model=List[admin_schema.PostSimpleAdminSchema])
def list_posts_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(Post).order_by(Post.create_date.desc()).limit(100).all()

from domain.push.push_service import send_push_to_all

# --- Push Notification Management (푸시 알림 관리) ---

@router.get("/push/subscriptions")
def list_push_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """모든 푸시 구독 목록 조회 (관리자용)"""
    # [방어 로직] User 테이블과 명시적으로 JOIN하여 정보를 가져옵니다.
    subs = db.query(models.PushSubscription).join(models.User, models.PushSubscription.user_id == models.User.id).all()
    result = []
    for s in subs:
        user = db.query(models.User).filter(models.User.id == s.user_id).first()
        result.append({
            "id": s.id,
            "user_id": s.user_id,
            "username": user.username if user else "Unknown",
            "real_name": user.real_name if user else "",
            "endpoint": s.endpoint[:80] + "...", # 프리뷰 길이를 조금 늘림
        })
    return result

@router.post("/push/send")
def admin_send_push(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
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

@router.delete("/push/subscriptions/{sub_id}")
def delete_push_subscription(
    sub_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
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
def admin_get_all_dayoffs(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
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
    admin: User = Depends(check_admin)
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
def list_service_registries(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(ServiceRegistry).all()

@router.post("/service-registries", response_model=admin_schema.ServiceRegistrySchema)
def create_service_registry(data: admin_schema.ServiceRegistryCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = ServiceRegistry(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-registries/{registry_id}")
def delete_service_registry(registry_id: str, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = db.query(ServiceRegistry).filter(ServiceRegistry.id == registry_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}

# 2. Service Engine (컴포넌트 버전)
@router.get("/service-engines", response_model=List[admin_schema.ServiceEngineSchema])
def list_service_engines(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(ServiceEngine).all()

@router.post("/service-engines", response_model=admin_schema.ServiceEngineSchema)
def create_service_engine(data: admin_schema.ServiceEngineCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = ServiceEngine(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-engines/{engine_id}")
def delete_service_engine(engine_id: str, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = db.query(ServiceEngine).filter(ServiceEngine.id == engine_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    db.delete(db_obj)
    db.commit()
    return {"message": "success"}

# 3. Service App (원자적 인스턴스)
@router.get("/service-apps", response_model=List[admin_schema.ServiceAppSchema])
def list_service_apps(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(ServiceApp).all()

@router.post("/service-apps", response_model=admin_schema.ServiceAppSchema)
def create_service_app(data: admin_schema.ServiceAppCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = ServiceApp(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.put("/service-apps/{app_id}", response_model=admin_schema.ServiceAppSchema)
def update_service_app(app_id: int, data: admin_schema.ServiceAppUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# 4. Service Instance (번들)
@router.get("/service-instances", response_model=List[admin_schema.ServiceInstanceSchema])
def list_service_instances(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(ServiceInstance).all()

@router.post("/service-instances", response_model=admin_schema.ServiceInstanceSchema)
def create_service_instance(data: admin_schema.ServiceInstanceCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = ServiceInstance(**data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.put("/service-instances/{instance_id}", response_model=admin_schema.ServiceInstanceSchema)
def update_service_instance(instance_id: int, data: admin_schema.ServiceInstanceUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_obj = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not db_obj: raise HTTPException(status_code=404)
    for k, v in data.dict(exclude_unset=True).items():
        setattr(db_obj, k, v)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.delete("/service-instances/{instance_id}")
def delete_service_instance(instance_id: int, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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



