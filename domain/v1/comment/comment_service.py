"""
============================================================================
[댓글 비즈니스 서비스 레이어 (domain/v1/comment/comment_service.py)]
============================================================================
"""

from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Comment, Post, User
from domain.v1.comment import comment_schema, comment_crud
from domain.v1.admin.service_service import enforce_post_service_permission


def _get_active_post_or_404(db: Session, post_id: int) -> Post:
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return post


def _get_comment_or_404(db: Session, comment_id: int) -> Comment:
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    return db_comment


def _ensure_comment_owner_or_admin(db_comment: Comment, current_user: User, action_label: str) -> None:
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if db_comment.user_id != current_user.id and user_rank < 4:
        raise HTTPException(status_code=403, detail=f"{action_label} 권한이 없습니다.")


def list_post_comments(db: Session, post_id: int, current_user: Optional[User]):
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "comment", action="read")
    return comment_crud.get_comments_by_post(db, post_id=post_id)


def create_post_comment(
    db: Session,
    post_id: int,
    comment_in: comment_schema.CommentCreate,
    current_user: User,
):
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "comment", action="write")

    created = comment_crud.create_comment(
        db, post_id=post_id, user_id=current_user.id, comment_in=comment_in
    )

    # 게시판 댓글/답글 알림 (core.notify 단일화: 알림함 적재 + WS + Web Push)
    board = post.board
    if board:
        from core.notify import safe_notify
        from domain.push.push_service import is_push_option_enabled

        commenter = current_user.real_name or current_user.username
        preview = (comment_in.content or "").strip().replace("\n", " ")[:60]
        target_url = f"/v1/app/board/{board.slug}/{post.id}"
        notified_user_ids: set[int] = set()

        if (
            post.user_id
            and post.user_id != current_user.id
            and is_push_option_enabled(board.options, "push_on_comment")
        ):
            notified_user_ids.add(post.user_id)
            safe_notify(
                db=db,
                category="NOTIFICATION",
                title=f"[{board.name}] 새 댓글",
                message=f"{commenter}: {preview}",
                sender=current_user,
                target_user_ids=[post.user_id],
                level=1,
                link=target_url,
                extra_payload={"send_web_push": True},
            )

        if created.parent_id and is_push_option_enabled(board.options, "push_on_reply"):
            parent_comment = db.query(Comment).filter(Comment.id == created.parent_id).first()
            if (
                parent_comment
                and parent_comment.user_id
                and parent_comment.user_id != current_user.id
                and parent_comment.user_id not in notified_user_ids
            ):
                safe_notify(
                    db=db,
                    category="NOTIFICATION",
                    title=f"[{board.name}] 내 댓글에 새 답글",
                    message=f"{commenter}: {preview}",
                    sender=current_user,
                    target_user_ids=[parent_comment.user_id],
                    level=1,
                    link=target_url,
                    extra_payload={"send_web_push": True},
                )

    return created


def update_post_comment(
    db: Session,
    comment_id: int,
    comment_in: comment_schema.CommentUpdate,
    current_user: User,
):
    db_comment = _get_comment_or_404(db, comment_id)
    if db_comment.post:
        enforce_post_service_permission(db, db_comment.post, current_user, "comment", action="write")
    _ensure_comment_owner_or_admin(db_comment, current_user, "수정")
    return comment_crud.update_comment(db, db_comment=db_comment, comment_in=comment_in)


def delete_post_comment(db: Session, comment_id: int, current_user: User) -> dict:
    db_comment = _get_comment_or_404(db, comment_id)
    if db_comment.post:
        enforce_post_service_permission(db, db_comment.post, current_user, "comment", action="write")
    _ensure_comment_owner_or_admin(db_comment, current_user, "삭제")
    comment_crud.delete_comment(db, db_comment=db_comment)
    return {"message": "success"}
