from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import User, UserProfile, BoardConfig, Post, Menu, SystemConfig, AppRegistry
from domain.user.user_router import get_current_user, get_current_user_optional, RankChecker, check_rank
from domain.v1.admin.admin_schema import (
    MenuCreate, MenuUpdate, MenuSchema, 
    BoardSimpleSchema, PostSimpleAdminSchema,
    BoardConfigCreate, BoardConfigUpdate, BoardConfigAdminSchema,
    UserAdminSchema, UserRankUpdate,
    AppRegistryCreate, AppRegistryUpdate, AppRegistrySchema
)
from typing import List, Optional, Any

router = APIRouter(
    prefix="/v1/admin",
    tags=["admin_v1"]
)

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

@router.get("/users", response_model=List[UserAdminSchema])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """전체 유저 목록 조회 (관리자용)"""
    return db.query(User).options(joinedload(User.profile)).all()

@router.get("/users/{user_id}", response_model=UserAdminSchema)
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
    rank_in: UserRankUpdate,
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

# --- System App Registry (시스템 앱 관리) ---

@router.get("/apps", response_model=List[AppRegistrySchema])
def list_apps(db: Session = Depends(get_db)):
    """설치된 앱 목록 조회 (전체 공개)"""
    return db.query(AppRegistry).all()

@router.post("/apps", response_model=AppRegistrySchema)
def create_app(app_in: AppRegistryCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """새로운 앱 등록"""
    if db.query(AppRegistry).filter(AppRegistry.app_id == app_in.app_id).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 App ID입니다.")
    db_app = AppRegistry(**app_in.dict())
    db.add(db_app)
    db.commit()
    db.refresh(db_app)
    return db_app

@router.put("/apps/{app_id}", response_model=AppRegistrySchema)
def update_app(app_id: str, app_in: AppRegistryUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """앱 정보 수정"""
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    for key, value in app_in.dict(exclude_unset=True).items():
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
    """메뉴 설정에 따른 최종 접속 URL 계산 (추상화의 핵심)"""
    if menu.link_type == "APP" and menu.app_id:
        # 1. 앱 엔진 메타데이터 조회
        app = db.query(AppRegistry).filter(AppRegistry.app_id == menu.app_id).first()
        if not app or not app.frontend_route:
            return menu.external_url or "#"
        
        # 2. 인스턴스 정보가 있는 경우 (예: 게시판 슬러그)
        if menu.app_instance_id:
            # 게시판 앱인 경우 특별 처리 (향후 다른 앱들도 확장 가능)
            if menu.app_id == "board":
                board = db.query(BoardConfig).filter(BoardConfig.id == menu.app_instance_id).first()
                if board:
                    # /board/[slug] -> /board/notice
                    return app.frontend_route.replace("[slug]", board.slug)
        
        # 3. 인스턴스 정보가 없는 앱 메인 경로
        return app.frontend_route.split("/[")[0] # /board/[slug] -> /board
        
    elif menu.link_type == "PAGE" and menu.page_id:
        return f"/v1/board/page/{menu.page_id}"
        
    return menu.external_url or "#"

def filter_menu_tree(menus: List[Menu], user_rank: int, db: Session):
    """재귀적 메뉴 필터링 및 동적 URL 주입"""
    filtered = []
    for m in menus:
        if m.is_visible and m.min_rank <= user_rank:
            # 동적 URL 계산
            final_url = resolve_menu_url(m, db)
            
            menu_data = {
                "id": m.id, "title": m.title, "parent_id": m.parent_id,
                "icon_name": m.icon_name, "icon_color": m.icon_color,
                "link_type": m.link_type, "external_url": final_url,
                "order": m.order, "is_visible": m.is_visible, "min_rank": m.min_rank,
                "app_id": m.app_id, "app_instance_id": m.app_instance_id,
                "sub_menus": filter_menu_tree(m.sub_menus, user_rank, db)
            }
            filtered.append(menu_data)
    return filtered

@router.get("/menu/public", response_model=List[MenuSchema])
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
    
    return filter_menu_tree(root_menus, user_rank, db)

@router.get("/menu", response_model=List[MenuSchema])
def get_all_menus(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """관리자용 전체 메뉴 트리"""
    return db.query(Menu).options(joinedload(Menu.sub_menus)).filter(Menu.parent_id == None).order_by(Menu.order).all()

@router.post("/menu", response_model=MenuSchema)
def create_menu(menu_in: MenuCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_menu = Menu(**menu_in.dict())
    db.add(db_menu)
    db.commit()
    db.refresh(db_menu)
    return db_menu

@router.put("/menu/{menu_id}", response_model=MenuSchema)
def update_menu(menu_id: int, menu_in: MenuUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)
    for key, value in menu_in.dict(exclude_unset=True).items():
        setattr(db_menu, key, value)
    db.commit()
    db.refresh(db_menu)
    return db_menu

@router.delete("/menu/{menu_id}")
def delete_menu(menu_id: int, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu: raise HTTPException(status_code=404)
    db.delete(db_menu)
    db.commit()
    return {"message": "success"}

# --- System Configuration ---

@router.get("/config")
def get_all_configs(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(SystemConfig).all()

@router.put("/config/{key}")
def update_config(key: str, value: Any = Body(...), db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        config = SystemConfig(key=key, value=value)
        db.add(config)
    else:
        config.value = value
    db.commit()
    return {"message": "success", "key": key, "value": value}

@router.get("/config/public")
def get_public_configs(db: Session = Depends(get_db)):
    configs = db.query(SystemConfig).all()
    return {c.key: c.value for c in configs}

# --- Board Configuration Management (게시판 설정 관리) ---

@router.get("/boards", response_model=List[BoardConfigAdminSchema])
def get_all_boards(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(BoardConfig).order_by(BoardConfig.id).all()

@router.post("/boards", response_model=BoardConfigAdminSchema)
def create_board_config(board_in: BoardConfigCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    if db.query(BoardConfig).filter(BoardConfig.slug == board_in.slug).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    db_board = BoardConfig(**board_in.dict())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.put("/boards/{board_id}", response_model=BoardConfigAdminSchema)
def update_board_config(board_id: int, board_in: BoardConfigUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
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

@router.get("/boards/list", response_model=List[BoardSimpleSchema])
def list_boards_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(BoardConfig).filter(BoardConfig.is_active == True).order_by(BoardConfig.name).all()

@router.get("/posts/list", response_model=List[PostSimpleAdminSchema])
def list_posts_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    return db.query(Post).order_by(Post.create_date.desc()).limit(100).all()
