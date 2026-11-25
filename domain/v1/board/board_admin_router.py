"""
[게시판 관리자 라우터 (domain/v1/board/board_admin_router.py)]
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from core.deps import require_app_permission
from domain.v1.admin import admin_schema
from models import BoardConfig, Post, User

router = APIRouter(tags=["Admin Board"])

check_board_admin = require_app_permission("board", action="read")
check_board_admin_write = require_app_permission("board", action="write")

DEFAULT_BOARD_META_KEYS = [
    "category", "is_pinned", "pin_until", "bg_tone", "title_bold",
    "title_color", "new_mode", "icon", "require_read_receipt", "publish_at",
    "expire_at", "target_groups", "push_on_create", "cta_label", "cta_url",
    "summary_line", "effective_date", "route_no", "vehicle_no",
    "is_secret", "hide_author", "allow_comment",
]


def _ensure_default_board_options(raw_options: Optional[dict]) -> dict:
    opts = dict(raw_options or {})
    if "use_pin" not in opts:
        opts["use_pin"] = {
            "label": "상단 고정 사용",
            "type": "toggle",
            "description": "공지글 상단 고정 기능 활성화",
            "value": True,
        }
    if "new_hours" not in opts:
        opts["new_hours"] = 24
    if "categories" not in opts:
        opts["categories"] = ["공지", "긴급", "필독", "안전", "정비", "일반"]
    if "view_meta_keys" not in opts:
        opts["view_meta_keys"] = list(DEFAULT_BOARD_META_KEYS)
    if "write_meta_keys" not in opts:
        opts["write_meta_keys"] = list(DEFAULT_BOARD_META_KEYS)
    return opts


@router.get("/boards", response_model=List[admin_schema.BoardConfigAdminSchema])
def get_all_boards(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(BoardConfig).order_by(BoardConfig.id).all()


@router.post("/boards", response_model=admin_schema.BoardConfigAdminSchema)
def create_board_config(
    board_in: admin_schema.BoardConfigCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_board_admin_write),
):
    if db.query(BoardConfig).filter(BoardConfig.slug == board_in.slug).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    payload = board_in.dict()
    payload["options"] = _ensure_default_board_options(payload.get("options"))
    db_board = BoardConfig(**payload)
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    return db_board


@router.put("/boards/{board_id}", response_model=admin_schema.BoardConfigAdminSchema)
def update_board_config(
    board_id: int,
    board_in: admin_schema.BoardConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_board_admin_write),
):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    for key, value in board_in.dict(exclude_unset=True).items():
        setattr(db_board, key, value)
    db.commit()
    db.refresh(db_board)
    return db_board


@router.delete("/boards/{board_id}")
def delete_board_config(
    board_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_board_admin_write),
):
    db_board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="게시판 설정을 찾을 수 없습니다.")
    db.delete(db_board)
    db.commit()
    return {"message": "success"}


@router.get("/boards/list", response_model=List[admin_schema.BoardSimpleSchema])
def list_boards_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(BoardConfig).filter(BoardConfig.is_active == True).order_by(BoardConfig.name).all()


@router.get("/posts/list", response_model=List[admin_schema.PostSimpleAdminSchema])
def list_posts_for_selection(db: Session = Depends(get_db), admin: User = Depends(check_board_admin)):
    return db.query(Post).order_by(Post.create_date.desc()).limit(100).all()
