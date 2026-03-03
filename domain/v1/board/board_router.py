from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from models import BoardConfig, Post, Menu, User
from domain.v1.board import board_schema, board_crud
from domain.user.user_router import get_current_user, get_current_user_optional, RankChecker
from typing import List, Optional

router = APIRouter(
    prefix="/v1/board",
    tags=["board_v1"]
)

# --- [지능형 보안 유틸리티] ---
def verify_access_by_menu(path: str, db: Session, current_user: Optional[User]):
    """
    [지능형 권한 상속: 최장 전방 일치(Longest Prefix Match)]
    1. 최고 관리자(Rank 4)는 무조건 통과합니다.
    2. 요청 경로가 메뉴의 URL로 시작하는지 확인하여 권한을 상속받습니다.
    3. 여러 메뉴가 겹칠 경우 가장 긴(구체적인) 경로의 설정을 따릅니다.
    """
    user_rank = current_user.rank() if (current_user and callable(current_user.rank)) else (current_user.rank if current_user else 0)

    # 0. 최고 관리자(Rank 4) 예외 처리
    if user_rank >= 4:
        return

    # 1. 경로 정규화 및 변환 (API 경로 -> 공개 경로)
    # 앞뒤 슬래시를 제거하여 비교하기 쉬운 형태로 만듦
    p = path.strip('/')
    p_public = p.replace("v1/board/list/", "board/").replace("create/", "board/").replace("/write", "")
    
    # 비교를 위해 다시 앞 슬래시를 붙인 정규화된 경로들
    targets = [f"/{p}", f"/{p_public}"]

    # 2. 모든 메뉴를 가져와서 '전방 일치' 여부 확인
    # 문자열 길이가 긴 순서대로 정렬하여 가장 구체적인 메뉴를 먼저 찾음
    menus = db.query(Menu).filter(Menu.external_url != None).order_by(Menu.external_url.desc()).all()
    
    matched_menu = None
    for m in menus:
        m_url = m.external_url.strip('/')
        m_url_slash = f"/{m_url}"
        
        # 사용자의 요청 경로(targets)가 메뉴 URL로 시작하는지 확인
        for t in targets:
            if t.startswith(m_url_slash):
                matched_menu = m
                break
        if matched_menu:
            break

    if matched_menu:
        # 매칭된 메뉴의 권한 체크
        if user_rank < matched_menu.min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{matched_menu.title}' 접근 권한 부족 (필요: Rank {matched_menu.min_rank}, 현재: {user_rank})"
            )
    else:
        # 3. 메뉴에 없으면 기본 보안 정책 (Rank 3 이상)
        if user_rank < 3:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="등록되지 않은 페이지이거나 접근 권한이 부족합니다. (관리자 문의)"
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
    verify_access_by_menu(f"/v1/board/list/{slug}", db, current_user)
    
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="존재하지 않는 게시판입니다.")
        
    total, posts = board_crud.get_post_list(
        db, board_id=board.id, skip=page * size, limit=size, user=current_user, keyword=keyword
    )
    
    return {"total": total, "posts": posts, "board": board}

@router.get("/post/{post_id}")
def get_post_detail(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """게시물 상세 조회 (보안 체크 + 조회수 증가)"""
    # 1. 게시물 및 게시판 정보 조회
    post = board_crud.get_post_detail(db, post_id=post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    
    # 2. 지능형 보안 체크 (해당 게시판의 리스트 접근 권한이 있는지 확인)
    verify_access_by_menu(f"/board/{post.board.slug}", db, current_user)
    
    # 3. 조회수 증가 (단순 증가)
    post.view_count += 1
    db.commit()
    
    # 4. 읽음 처리 (로그인 유저인 경우)
    if current_user:
        # PostRead 로직은 crud에 분리 가능하지만 여기선 일단 직접 처리
        from models import PostRead
        read_history = db.query(PostRead).filter(
            PostRead.post_id == post.id, 
            PostRead.user_id == current_user.id
        ).first()
        if not read_history:
            db.add(PostRead(post_id=post.id, user_id=current_user.id))
            db.commit()

    return post

@router.post("/create/{slug}")
def post_create(
    slug: str,
    post_in: board_schema.PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """게시물 생성 (보안 체크 + 에디터 타입 검증)"""
    # 1. 지능형 보안 체크 (글쓰기 페이지 권한 상속)
    verify_access_by_menu(f"/board/{slug}/write", db, current_user)
    
    # 2. 게시판 설정 조회
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="게시판을 찾을 수 없습니다.")
        
    # 3. 글쓰기 허용 여부 체크
    if board.options.get("editor_type") == "none":
        raise HTTPException(status_code=403, detail="이 게시판은 글쓰기가 허용되지 않습니다.")
        
    # 4. 생성 실행
    return board_crud.create_post(db, board_id=board.id, user_id=current_user.id, post_in=post_in)

@router.get("/landing", response_model=board_schema.LandingPageResponse)
def get_landing_info(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """랜딩 페이지 정보"""
    verify_access_by_menu("/v1/board/landing", db, current_user)
    
    landing_config = db.query(BoardConfig).filter(BoardConfig.slug == "landing").first()
    if not landing_config:
        return {"message": "landing config not found"}

    landing_post = db.query(Post).filter(
        Post.board_id == landing_config.id,
        Post.status == "published",
        Post.is_deleted == False
    ).order_by(Post.create_date.desc()).first()

    return {"config": landing_config, "post": landing_post, "message": "success"}
