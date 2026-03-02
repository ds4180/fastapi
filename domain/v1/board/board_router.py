from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from models import BoardConfig, Post, Menu, User
from domain.v1.board import board_schema, board_crud
from domain.user.user_router import get_current_user_optional, RankChecker
from typing import List, Optional

router = APIRouter(
    prefix="/v1/board",
    tags=["board_v1"]
)

# --- [지능형 보안 유틸리티] ---
def verify_access_by_menu(path: str, db: Session, current_user: Optional[User]):
    """
    [지능형 권한 상속 개선]
    1. API 경로(/v1/board/list/slug)와 공개 경로(/board/slug) 모두를 메뉴에서 검색합니다.
    """
    user_rank = current_user.rank() if (current_user and callable(current_user.rank)) else (current_user.rank if current_user else 0)

    # 경로 정규화 (앞 슬래시 보장)
    p = path if path.startswith('/') else f"/{path}"

    # 💡 지능형 매핑: API 경로를 공개 경로로 변환하여 한 번 더 찾아봄
    # 예: /v1/board/list/normal -> /board/normal
    public_path = p.replace("/v1/board/list/", "/board/")

    # 두 경로 중 하나라도 메뉴에 있으면 그 등급을 따름
    menu = db.query(Menu).filter(
        or_(Menu.external_url == p, Menu.external_url == public_path)
    ).first()

    if menu:
        if user_rank < menu.min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"이 페이지는 Rank {menu.min_rank} 이상만 접근 가능합니다. (현재 Rank: {user_rank})"
            )
    else:
        # 메뉴에 없으면 기본 Rank 3 적용
        if user_rank < 3:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="메뉴에 등록되지 않은 비공개 페이지입니다. (관리자 문의)"
            )


# --- API Endpoints ---

@router.get("/list/{slug}", response_model=board_schema.PostListSchema)
def get_board_posts(
    slug: str, 
    page: int = 0,
    size: int = 10,
    keyword: str = "",
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """게시판 목록 조회 (지능형 권한 체크 + 페이징 + 검색)"""
    # 1. 지능형 권한 체크 (메뉴 기준)
    verify_access_by_menu(f"/v1/board/list/{slug}", db, current_user)
    
    # 2. 게시판 존재 확인
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="존재하지 않는 게시판입니다.")
        
    # 3. CRUD 호출 (M2M 정보 포함)
    total, posts = board_crud.get_post_list(
        db, 
        board_id=board.id, 
        skip=page * size, 
        limit=size, 
        user=current_user, 
        keyword=keyword
    )
    
    return {
        "total": total,
        "posts": posts,
        "board": board
    }

@router.get("/landing", response_model=board_schema.LandingPageResponse)
def get_landing_info(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """랜딩 페이지 정보 (공개 페이지 권한 체크)"""
    verify_access_by_menu("/v1/board/landing", db, current_user)
    
    landing_config = db.query(BoardConfig).filter(BoardConfig.slug == "landing").first()
    if not landing_config:
        return {"message": "landing config not found"}

    landing_post = db.query(Post).filter(
        Post.board_id == landing_config.id,
        Post.status == "published",
        Post.is_deleted == False
    ).order_by(Post.create_date.desc()).first()

    return {
        "config": landing_config,
        "post": landing_post,
        "message": "success"
    }
