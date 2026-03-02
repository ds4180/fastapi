from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import BoardConfig, Post, Menu, User
from domain.v1.board import board_schema
from domain.user.user_router import get_current_user_optional, RankChecker
from typing import List, Optional

router = APIRouter(
    prefix="/v1/board",
    tags=["board_v1"]
)

# --- [지능형 보안 유틸리티] ---

def verify_access_by_menu(path: str, db: Session, current_user: Optional[User]):
    """
    [사용자 요청 반영: 지능형 권한 상속]
    1. 요청된 경로(path)와 연결된 메뉴 설정을 DB에서 찾습니다.
    2. 메뉴에 설정된 min_rank를 가져옵니다.
    3. 메뉴에 등록되지 않은 경로는 보안을 위해 기본적으로 Rank 4(최고관리자)만 접근 가능하게 제한합니다.
    """
    # 현재 사용자 랭크 (비로그인 0)
    user_rank = current_user.rank() if (current_user and callable(current_user.rank)) else (current_user.rank if current_user else 0)
    
    # 해당 주소와 연결된 메뉴 조회
    # (앞뒤 슬래시 등 주소 정규화 고려)
    target_path = path if path.startswith('/') else f"/{path}"
    menu = db.query(Menu).filter(Menu.external_url == target_path).first()
    
    if menu:
        # 메뉴가 있다면 메뉴 등급을 따름
        if user_rank < menu.min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"이 페이지는 Rank {menu.min_rank} 이상만 접근 가능합니다. (현재 Rank: {user_rank})"
            )
    else:
        # 🚨 메뉴에 등록되지 않은 '고립된' 페이지는 보안상 책임 관리자(Rank 3) 이상 접근 허용
        if user_rank < 3:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="메뉴에 등록되지 않은 비공개 페이지입니다. 관리자에게 문의하세요."
            )

# --- API Endpoints ---

@router.get("/list/{slug}")
def get_board_posts(
    slug: str, 
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """게시판 목록 조회 (지능형 권한 체크 적용)"""
    # 1. 이 주소(/v1/board/list/slug)에 대한 권한을 메뉴 설정에서 역추적하여 검증
    verify_access_by_menu(f"/v1/board/list/{slug}", db, current_user)
    
    # 2. 권한 통과 시 데이터 조회
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="존재하지 않는 게시판입니다.")
        
    posts = db.query(Post).filter(Post.board_id == board.id, Post.is_deleted == False).all()
    return {"board": board, "posts": posts}

@router.get("/landing", response_model=board_schema.LandingPageResponse)
def get_landing_info(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """랜딩 페이지 정보 (공개 페이지 권한 체크)"""
    # 랜딩 페이지는 보통 메뉴 Rank 0으로 등록되어 있을 것이므로 자연스럽게 통과됨
    # 만약 메뉴에 등록 안 했다면? Rank 4만 보게 됨 (의도된 설계)
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
