from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, cast, String, text
from models import AppRegistry, Post, BoardConfig, User, PostRead, Comment, PostReaction, MediaAsset
from domain.v1.board.board_schema import PostCreate, PostUpdate
from core.permission import get_user_rank
from typing import Any, Dict, List, Optional

PRIVILEGED_META_KEYS = {
    "is_pinned",
    "pin_until",
    "bg_tone",
    "title_bold",
    "title_color",
    "new_mode",
    "require_read_receipt",
    "target_groups",
    "push_on_create",
    "publish_at",
    "expire_at",
    "cta_url",
    "cta_label",
}


def _parse_iso_dt(val: Any) -> Optional[datetime]:
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d")
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _parse_group_list(raw: Any) -> set[str]:
    if isinstance(raw, (list, set, tuple)):
        return {str(g).strip() for g in raw if str(g).strip()}
    if isinstance(raw, str) and raw.strip():
        return {s.strip() for s in raw.split(",") if s.strip()}
    return set()


def get_board_admin_rank(db: Optional[Session] = None) -> int:
    """상위 앱('board')의 min_write_rank를 게시판 관리자 기준 랭크로 조회합니다 (기본 4)."""
    if db is not None:
        row = db.query(AppRegistry.min_write_rank).filter(AppRegistry.app_id == "board").first()
        if row and row[0] is not None:
            return int(row[0])
        return 4
    try:
        from database import SessionLocal
        with SessionLocal() as tmp_db:
            row = tmp_db.query(AppRegistry.min_write_rank).filter(AppRegistry.app_id == "board").first()
            if row and row[0] is not None:
                return int(row[0])
    except Exception:
        pass
    return 4


def is_board_admin(
    user: Optional[User],
    board: Optional[BoardConfig] = None,
    db: Optional[Session] = None,
    admin_rank: Optional[int] = None,
) -> bool:
    """상위 앱('board')의 쓰기 랭크(min_write_rank) 이상이거나 게시판 admin_groups 소속이면 True."""
    if not user:
        return False
    required_rank = admin_rank if admin_rank is not None else get_board_admin_rank(db)
    if get_user_rank(user) >= required_rank:
        return True
    if not board:
        return False

    user_groups = _get_user_group_codes(user)
    if not user_groups:
        return False

    opts = getattr(board, "options", None) or {}
    admin_groups = _parse_group_list(opts.get("admin_groups"))

    allow_groups = getattr(board, "allow_groups", None)
    if isinstance(allow_groups, dict):
        admin_groups |= _parse_group_list(allow_groups.get("admin"))

    return bool(admin_groups & user_groups)


def sanitize_post_extra_data(
    raw_extra: Optional[Dict[str, Any]],
    user: Optional[User],
    board: Optional[BoardConfig] = None,
    db: Optional[Session] = None,
    admin_rank: Optional[int] = None,
) -> Dict[str, Any]:
    """작성자 권한(또는 게시판 전용 관리자 그룹)에 따라 허용된 게시물 메타데이터만 정제해 반환합니다."""
    if not isinstance(raw_extra, dict):
        return {}
    is_admin = is_board_admin(user, board, db=db, admin_rank=admin_rank)
    cleaned: Dict[str, Any] = {}
    for k, v in raw_extra.items():
        if not is_admin and k in PRIVILEGED_META_KEYS:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                continue
        if v is False and k in ("is_pinned", "title_bold", "is_secret", "require_read_receipt", "hide_author", "push_on_create"):
            continue
        if v is None:
            continue
        cleaned[k] = v
    return cleaned


def _get_user_group_codes(user: Optional[User]) -> set[str]:
    if not user or not getattr(user, "profile", None):
        return set()
    codes: set[str] = set()
    if user.profile.primary_group:
        codes.add(str(user.profile.primary_group).strip())
    if isinstance(user.profile.secondary_groups, list):
        for g in user.profile.secondary_groups:
            if g:
                codes.add(str(g).strip())
    return codes


def can_view_post(
    post: Post,
    user: Optional[User],
    board: Optional[BoardConfig] = None,
    db: Optional[Session] = None,
    admin_rank: Optional[int] = None,
) -> bool:
    """비밀글, 예약게시, 만료일, 대상 그룹 메타데이터 기반 열람 권한을 판별합니다."""
    target_board = board or getattr(post, "board", None)
    if user and (post.user_id == user.id or is_board_admin(user, target_board, db=db, admin_rank=admin_rank)):
        return True

    extra = post.extra_data if isinstance(post.extra_data, dict) else {}
    if extra.get("is_secret"):
        return False

    now = datetime.now()
    publish_dt = _parse_iso_dt(extra.get("publish_at"))
    if publish_dt and now < publish_dt:
        return False

    expire_raw = extra.get("expire_at")
    expire_dt = _parse_iso_dt(expire_raw)
    if expire_dt:
        if isinstance(expire_raw, str) and len(expire_raw.strip()) == 10:
            expire_dt = expire_dt.replace(hour=23, minute=59, second=59)
        if now > expire_dt:
            return False

    target_groups = extra.get("target_groups")
    if isinstance(target_groups, list):
        normalized = {str(g).strip() for g in target_groups if str(g).strip()}
        if normalized:
            user_groups = _get_user_group_codes(user)
            if not (normalized & user_groups):
                return False

    return True


def is_post_effectively_pinned(post: Post, today_str: Optional[str] = None) -> bool:
    """상단 고정 및 고정 만료일(pin_until) 유효 여부를 판별합니다."""
    extra = post.extra_data if isinstance(post.extra_data, dict) else {}
    if not extra.get("is_pinned"):
        return False
    pin_until = str(extra.get("pin_until") or "").strip()
    if pin_until:
        today_s = today_str or datetime.now().strftime("%Y-%m-%d")
        if pin_until[:10] < today_s:
            return False
    return True


def mask_post_author_name(
    post: Post,
    user: Optional[User],
    board: Optional[BoardConfig] = None,
    db: Optional[Session] = None,
    admin_rank: Optional[int] = None,
) -> str:
    """작성자 비공개(hide_author) 메타 적용 시 작성자명을 마스킹합니다."""
    real_name = (post.user.real_name or post.user.username) if post.user else "탈퇴한 사용자"
    extra = post.extra_data if isinstance(post.extra_data, dict) else {}
    target_board = board or getattr(post, "board", None)
    if extra.get("hide_author"):
        if not user or (post.user_id != user.id and not is_board_admin(user, target_board, db=db, admin_rank=admin_rank)):
            return "비공개"
    return real_name


def is_board_pin_enabled(board_options: Optional[Dict[str, Any]]) -> bool:
    """게시판 options에서 상단 고정 기능(use_pin) 활성화 여부를 반환합니다."""
    if not isinstance(board_options, dict) or "use_pin" not in board_options:
        return True
    raw = board_options.get("use_pin")
    if isinstance(raw, dict) and "value" in raw:
        return bool(raw.get("value"))
    return bool(raw)


def get_post_list(
    db: Session,
    board_id: int,
    skip: int = 0,
    limit: int = 10,
    user: User = None,
    keyword: str = "",
    sort: str = "latest",
    category: str = "",
    use_pin: bool = True,
    board: Optional[BoardConfig] = None,
):
    if board is None:
        board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
    query = db.query(Post).filter(
        Post.board_id == board_id,
        Post.is_deleted == False
    )

    if keyword:
        search = f"%{keyword}%"
        kw_clean = keyword.strip()
        conds = [
            Post.title.ilike(search),
            Post.content.ilike(search),
            User.username.ilike(search),
            User.real_name.ilike(search),
            cast(Post.extra_data, String).ilike(search),
        ]
        if kw_clean.isdigit():
            conds.append(Post.board_seq == int(kw_clean))
        query = query.outerjoin(User).filter(or_(*conds)).distinct()

    if sort == "views":
        order_clause = Post.view_count.desc()
    elif sort == "oldest":
        order_clause = Post.create_date.asc()
    else:
        order_clause = Post.create_date.desc()

    all_posts = query.order_by(order_clause, Post.id.desc()).all()

    cat_filter = (category or "").strip()
    admin_rank = get_board_admin_rank(db)
    visible_posts: List[Post] = []
    for p in all_posts:
        if not can_view_post(p, user, board, db=db, admin_rank=admin_rank):
            continue
        if cat_filter and cat_filter != "전체":
            p_extra = p.extra_data if isinstance(p.extra_data, dict) else {}
            if str(p_extra.get("category") or "").strip() != cat_filter:
                continue
        visible_posts.append(p)

    if use_pin:
        today_str = datetime.now().strftime("%Y-%m-%d")
        visible_posts.sort(key=lambda p: 0 if is_post_effectively_pinned(p, today_str) else 1)

    total = len(visible_posts)
    posts = visible_posts[skip : skip + limit]

    result_posts = []
    for post in posts:
        post_data = {
            "id": post.id,
            "board_seq": post.board_seq,
            "title": post.title,
            "content": post.content,
            "content_json": post.content_json,
            "extra_data": post.extra_data or {},
            "status": post.status,
            "view_count": post.view_count,
            "create_date": post.create_date,
            "user_name": mask_post_author_name(post, user, board, db=db, admin_rank=admin_rank),
            "is_read": False,
            "like_count": len(post.reactions),
            "comment_count": len(post.comments)
        }

        if user:
            is_read = db.query(PostRead).filter(
                PostRead.post_id == post.id,
                PostRead.user_id == user.id
            ).first()
            post_data["is_read"] = True if is_read else False

        result_posts.append(post_data)

    return total, result_posts

def create_post(db: Session, board_id: int, user_id: int, post_in: PostCreate):
    """새 게시물 생성 (게시판별 독립 문서번호 채번 + MediaAsset 연동 포함)"""
    seq_row = db.execute(
        text(
            "UPDATE board_config SET next_seq = next_seq + 1 "
            "WHERE id = :board_id RETURNING next_seq - 1"
        ),
        {"board_id": board_id},
    ).first()
    if seq_row and seq_row[0] is not None:
        board_seq = int(seq_row[0])
    else:
        max_seq = db.query(func.coalesce(func.max(Post.board_seq), 0)).filter(Post.board_id == board_id).scalar()
        board_seq = int(max_seq or 0) + 1

    db_post = Post(
        board_id=board_id,
        board_seq=board_seq,
        user_id=user_id,
        title=post_in.title,
        content=post_in.content,
        content_json=post_in.content_json,
        extra_data=post_in.extra_data,
        status=post_in.status,
        create_date=datetime.now()
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)

    # ⚠️ 업로드된 미디어 자산 연동 (MediaAsset.target_id 업데이트)
    if post_in.media_ids:
        db.query(MediaAsset).filter(
            MediaAsset.id.in_(post_in.media_ids),
            MediaAsset.user_id == user_id
        ).update({
            "app_id": "board",
            "target_id": str(db_post.id)
        }, synchronize_session=False)
        db.commit()

    return db_post

def get_post_detail(db: Session, post_id: int):
    """게시물 상세 조회"""
    return db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()

def update_post(db: Session, db_post: Post, post_in: PostUpdate):
    """게시물 수정 (MediaAsset 연동 포함)"""
    update_data = post_in.dict(exclude_unset=True)
    media_ids = update_data.pop("media_ids", None)

    for key, value in update_data.items():
        setattr(db_post, key, value)
    
    db_post.modify_date = datetime.now()

    # ⚠️ 수정 시 추가된 미디어 자산 연동
    if media_ids:
        db.query(MediaAsset).filter(
            MediaAsset.id.in_(media_ids),
            MediaAsset.user_id == db_post.user_id
        ).update({
            "app_id": "board",
            "target_id": str(db_post.id)
        }, synchronize_session=False)

    db.commit()
    db.refresh(db_post)
    return db_post

def delete_post(db: Session, db_post: Post):
    """게시물 삭제 (Soft Delete + 게시물 및 소속 댓글의 MediaAsset 소프트 삭제 및 격리 큐 예약)"""
    from domain.media import media_service

    db_post.is_deleted = True
    db_post.delete_date = datetime.now()

    linked_assets = db.query(MediaAsset).filter(
        MediaAsset.app_id == "board",
        MediaAsset.target_id == str(db_post.id),
        MediaAsset.is_deleted == False
    ).all()
    for asset in linked_assets:
        media_service.delete_asset(db, asset.id)

    comment_ids = [
        str(cid) for (cid,) in db.query(Comment.id).filter(Comment.post_id == db_post.id).all()
    ]
    if comment_ids:
        comment_assets = db.query(MediaAsset).filter(
            MediaAsset.app_id == "comment",
            MediaAsset.target_id.in_(comment_ids),
            MediaAsset.is_deleted == False
        ).all()
        for asset in comment_assets:
            media_service.delete_asset(db, asset.id)

    db.commit()
    return True
