from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import User, UserProfile, BoardConfig, Post, Menu, SystemConfig, AppRegistry, DayOff, ServiceRegistry, ServiceEngine, ServiceApp, ServiceInstance
from domain.user.user_router import get_current_user, get_current_user_optional, RankChecker, check_rank
from domain.v1.admin import admin_schema
from typing import List, Optional, Any
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
