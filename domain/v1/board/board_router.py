from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from models import BoardConfig, Post, User
from domain.v1.board import board_schema, board_crud
from core.deps import get_current_user, get_current_user_optional
from core.permission import can_access_board, get_user_rank
from core.view_counter import should_count_view
from typing import List, Optional

router = APIRouter(
    prefix="/v1/board",
    tags=["board_v1"]
)


# --- API Endpoints ---

@router.get("/list/{slug}", response_model=board_schema.PostListSchema)
def get_board_posts(
    slug: str, 
    page: int = 0,
    size: int = 10,
    keyword: str = "",
    sort: str = "latest",
    category: str = "",
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """게시판 목록 조회 (4단계 권한 체크 + 페이징 + 검색)"""
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="존재하지 않는 게시판입니다.")
    
    # 🛡️ [정책재정의.md 4단계 권한 입구 검문: 1.root ➔ 2.deny ➔ 3.allow ➔ 4.min_read_rank]
    if not can_access_board(current_user, board, action="read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{board.name}' 게시판 목록 열람 권한이 없습니다."
        )
    
    # 기능 활성화 체크 (List)
    if not board.options.get("use_list", True):
        if get_user_rank(current_user) < 4:
            raise HTTPException(status_code=403, detail="이 게시판은 목록 조회가 비활성화되어 있습니다.")
        
    total, posts = board_crud.get_post_list(
        db,
        board_id=board.id,
        skip=page * size,
        limit=size,
        user=current_user,
        keyword=keyword,
        sort=sort,
        category=category,
        use_pin=board_crud.is_board_pin_enabled(board.options),
    )
    
    return {"total": total, "posts": posts, "board": board}

@router.get("/post/{post_id}")
def get_post_detail(
    post_id: int,
    request: Request,
    count_view: bool = True,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """게시물 상세 조회 (보안 체크 + 조회수 증가)"""
    # 1. 게시물 및 게시판 정보 조회
    post = board_crud.get_post_detail(db, post_id=post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    
    # 🛡️ [정책재정의.md 4단계 권한 입구 검문: 1.root ➔ 2.deny ➔ 3.allow ➔ 4.min_read_rank]
    if not can_access_board(current_user, post.board, action="read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{post.board.name}' 게시물 열람 권한이 없습니다."
        )
    
    # 2. 상세 보기 비활성화 및 게시물 메타(비밀글/예약/만료/그룹) 체크
    if not post.board.options.get("use_view", True):
        if get_user_rank(current_user) < 4:
            raise HTTPException(status_code=403, detail="이 게시판은 상세 보기가 비활성화되어 있습니다.")

    if not board_crud.can_view_post(post, current_user, post.board, db=db):
        raise HTTPException(status_code=403, detail="이 게시물을 열람할 권한이 없거나 게시 기간이 아닙니다.")

    # 3. 조회수 증가 (Redis 24시간 TTL 중복 방지 + 원자적 증가)
    if count_view and should_count_view("post", post.id, request, current_user):
        db.query(Post).filter(Post.id == post.id).update({Post.view_count: Post.view_count + 1})
        db.commit()
        db.refresh(post)
    
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

    setattr(post, "user_name", board_crud.mask_post_author_name(post, current_user, post.board, db=db))

    return post

@router.post("/create/{slug}")
def post_create(
    slug: str,
    post_in: board_schema.PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """게시물 생성 (4단계 권한 체크 + 에디터 타입 검증)"""
    # 1. 게시판 설정 조회
    board = db.query(BoardConfig).filter(BoardConfig.slug == slug).first()
    if not board:
        raise HTTPException(status_code=404, detail="게시판을 찾을 수 없습니다.")

    # 🛡️ [정책재정의.md 4단계 권한 입구 검문: 1.root ➔ 2.deny ➔ 3.allow ➔ 4.min_write_rank]
    if not can_access_board(current_user, board, action="write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{board.name}' 게시판 글 작성 권한이 없습니다."
        )
        
    # 2. 글쓰기 허용 여부 체크
    if board.options.get("editor_type") == "none":
        raise HTTPException(status_code=403, detail="이 게시판은 글쓰기가 허용되지 않습니다.")

    if not board.options.get("use_write", True):
        if get_user_rank(current_user) < 4:
            raise HTTPException(status_code=403, detail="이 게시판은 글 작성이 비활성화되어 있습니다.")
        
    # 3. 메타데이터 권한 필터링 및 생성 실행
    post_in.extra_data = board_crud.sanitize_post_extra_data(post_in.extra_data, current_user, board=board, db=db)
    created = board_crud.create_post(db, board_id=board.id, user_id=current_user.id, post_in=post_in)
    from core.audit import safe_log_audit
    safe_log_audit(
        db=db,
        app_id="board",
        log_type="CHANGE",
        action="POST_CREATE",
        title=f"[{board.name}] 게시글 작성: {post_in.title}",
        user=current_user,
        resource_type="board_post",
        resource_id=str(getattr(created, "id", "")),
    )

    # 5. 🔔 [통합 알림] 게시판 푸시 옵션(push_on_post) 활성화 시 열람 권한자 대상 알림함 + 푸시 발송
    from core.notify import safe_notify
    from domain.push.push_service import is_push_option_enabled

    should_push = is_push_option_enabled(board.options, "push_on_post") or bool(
        board_crud.is_board_admin(current_user, board, db=db) and (created.extra_data or {}).get("push_on_create")
    )
    if should_push:
        author_name = current_user.real_name or current_user.username
        safe_notify(
            db=db,
            category="NOTIFICATION",
            title=f"[{board.name}] 새 게시글",
            message=f"{post_in.title} · {author_name}",
            sender=current_user,
            target_board_id=board.id,
            exclude_user_id=current_user.id,
            level=1,
            link=f"/v1/app/board/{slug}/{created.id}",
            extra_payload={"send_web_push": True},
        )

    return created

@router.put("/update/{post_id}")
def post_update(
    post_id: int,
    post_in: board_schema.PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """게시물 수정 (작성자 또는 관리자 확인)"""
    db_post = board_crud.get_post_detail(db, post_id=post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    
    # 🛡️ [정책재정의.md 4단계 권한 입구 검문: 1.root ➔ 2.deny ➔ 3.allow ➔ 4.min_write_rank]
    if not can_access_board(current_user, db_post.board, action="write"):
        raise HTTPException(status_code=403, detail="이 게시판에 대한 글 수정 권한이 없습니다.")

    # 권한 체크: 작성자 본인이거나 운영/게시판 전용 관리자
    if db_post.user_id != current_user.id and not board_crud.is_board_admin(current_user, db_post.board, db=db):
        raise HTTPException(status_code=403, detail="본인이 작성한 글만 수정할 수 있습니다.")

    if post_in.extra_data is not None:
        post_in.extra_data = board_crud.sanitize_post_extra_data(post_in.extra_data, current_user, board=db_post.board, db=db)

    updated = board_crud.update_post(db, db_post=db_post, post_in=post_in)
    from core.audit import safe_log_audit
    safe_log_audit(
        db=db,
        app_id="board",
        log_type="CHANGE",
        action="POST_UPDATE",
        title=f"게시글 수정 (#{post_id})",
        user=current_user,
        resource_type="board_post",
        resource_id=str(post_id),
    )
    return updated

@router.delete("/delete/{post_id}")
def post_delete(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """게시물 삭제 (작성자 또는 관리자 확인)"""
    db_post = board_crud.get_post_detail(db, post_id=post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    
    # 🛡️ [정책재정의.md 4단계 권한 입구 검문]
    if not can_access_board(current_user, db_post.board, action="write"):
        raise HTTPException(status_code=403, detail="이 게시판에 대한 글 삭제 권한이 없습니다.")

    # 권한 체크: 작성자 본인이거나 운영/게시판 전용 관리자
    if db_post.user_id != current_user.id and not board_crud.is_board_admin(current_user, db_post.board, db=db):
        raise HTTPException(status_code=403, detail="본인이 작성한 글만 삭제할 수 있습니다.")
        
    board_crud.delete_post(db, db_post=db_post)
    from core.audit import safe_log_audit
    safe_log_audit(
        db=db,
        app_id="board",
        log_type="CHANGE",
        action="POST_DELETE",
        title=f"게시글 삭제 (#{post_id})",
        user=current_user,
        resource_type="board_post",
        resource_id=str(post_id),
    )
    return {"message": "success"}

@router.get("/landing", response_model=board_schema.LandingPageResponse)
def get_landing_info(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """랜딩 페이지 정보"""
    landing_config = db.query(BoardConfig).filter(BoardConfig.slug == "landing").first()
    if not landing_config:
        return {"message": "landing config not found"}

    if not can_access_board(current_user, landing_config, action="read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="랜딩 게시판 열람 권한이 없습니다."
        )

    landing_post = db.query(Post).filter(
        Post.board_id == landing_config.id,
        Post.status == "published",
        Post.is_deleted == False
    ).order_by(Post.create_date.desc()).first()

    return {"config": landing_config, "post": landing_post, "message": "success"}
