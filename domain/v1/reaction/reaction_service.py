"""
============================================================================
[게시글 반응 비즈니스 서비스 레이어 (domain/v1/reaction/reaction_service.py)]
============================================================================
"""

from typing import Optional, Dict
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Post, PostReaction, User
from domain.v1.admin.service_service import enforce_post_service_permission


def _get_active_post_or_404(db: Session, post_id: int) -> Post:
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return post


def _build_reaction_summary(db: Session, post_id: int, user_id: Optional[int]) -> dict:
    rows = (
        db.query(PostReaction.reaction_type, func.count(PostReaction.user_id))
        .filter(PostReaction.post_id == post_id)
        .group_by(PostReaction.reaction_type)
        .all()
    )
    counts: Dict[str, int] = {str(rtype): int(cnt) for rtype, cnt in rows}
    my_reaction: Optional[str] = None
    if user_id is not None:
        mine = (
            db.query(PostReaction)
            .filter(PostReaction.post_id == post_id, PostReaction.user_id == user_id)
            .first()
        )
        if mine:
            my_reaction = mine.reaction_type

    return {
        "post_id": post_id,
        "counts": counts,
        "my_reaction": my_reaction,
        "total": sum(counts.values()),
    }


def get_reaction_summary(db: Session, post_id: int, current_user: Optional[User]) -> dict:
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "reaction", action="read")
    return _build_reaction_summary(db, post_id, current_user.id if current_user else None)


def toggle_reaction(db: Session, post_id: int, reaction_type: str, current_user: User) -> dict:
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "reaction", action="write")

    rtype = (reaction_type or "like").strip().lower()
    existing = (
        db.query(PostReaction)
        .filter(PostReaction.post_id == post_id, PostReaction.user_id == current_user.id)
        .first()
    )

    if existing:
        if existing.reaction_type == rtype:
            db.delete(existing)
        else:
            existing.reaction_type = rtype
    else:
        db.add(PostReaction(user_id=current_user.id, post_id=post_id, reaction_type=rtype))

    db.commit()
    return _build_reaction_summary(db, post_id, current_user.id)
