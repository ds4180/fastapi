from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import User, BoardConfig, Post, Menu, SystemConfig
from domain.user.user_router import get_current_user, get_current_user_optional, RankChecker, check_rank
from domain.v1.admin.admin_schema import (
    MenuCreate, MenuUpdate, MenuSchema, 
    BoardSimpleSchema, PostSimpleAdminSchema,
    BoardConfigCreate, BoardConfigUpdate, BoardConfigAdminSchema
)
from typing import List, Optional, Any

router = APIRouter(
    prefix="/v1/admin",
    tags=["admin_v1"]
)

# 편리한 최고 관리자 체크 의존성 (사용자 요청에 따라 Rank 4 기준)
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
    
    return {
        "user_count": user_count,
        "board_count": board_count,
        "post_count": post_count,
        "admin_name": admin.real_name or admin.username
    }

# --- Menu Management (메뉴 관리) ---

def filter_menu_tree(menus: List[Menu], user_rank: int):
    """재귀적 메뉴 필터링"""
    filtered = []
    for m in menus:
        if m.is_visible and m.min_rank <= user_rank:
            menu_data = {
                "id": m.id, "title": m.title, "parent_id": m.parent_id,
                "icon_name": m.icon_name, "icon_color": m.icon_color,
                "link_type": m.link_type, "external_url": m.external_url,
                "order": m.order, "is_visible": m.is_visible, "min_rank": m.min_rank,
                "sub_menus": filter_menu_tree(m.sub_menus, user_rank)
            }
            filtered.append(menu_data)
    return filtered

@router.get("/menu/public", response_model=List[MenuSchema])
def get_public_menus(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """일반 사용자용 공개 메뉴 조회 (Rank 기반 필터링)"""
    user_rank = 0
    if current_user:
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    
    root_menus = db.query(Menu).options(joinedload(Menu.sub_menus)).filter(
        Menu.parent_id == None, Menu.is_visible == True, Menu.min_rank <= user_rank
    ).order_by(Menu.order).all()
    
    return filter_menu_tree(root_menus, user_rank)

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
    """관리자용 전체 게시판 설정 목록"""
    return db.query(BoardConfig).order_by(BoardConfig.id).all()

@router.post("/boards", response_model=BoardConfigAdminSchema)
def create_board_config(board_in: BoardConfigCreate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """새 게시판 설정 생성"""
    if db.query(BoardConfig).filter(BoardConfig.slug == board_in.slug).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    
    db_board = BoardConfig(**board_in.dict())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    return db_board

@router.put("/boards/{board_id}", response_model=BoardConfigAdminSchema)
def update_board_config(board_id: int, board_in: BoardConfigUpdate, db: Session = Depends(get_db), admin: User = Depends(check_admin)):
    """게시판 설정 수정"""
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
    """게시판 설정 삭제"""
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
