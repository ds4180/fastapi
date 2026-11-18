from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict

from database import get_db
from models import Post, PostReaction, User
from core.deps import get_current_user_optional
from domain.user.user_router import get_current_user

router = APIRouter(
    prefix="/v1/reaction",
    tags=["reaction"],
)


class ReactionToggleRequest(BaseModel):
    reaction_type: str = "like"


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


@router.get("/{post_id}")
def get_post_reactions(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return _build_reaction_summary(db, post_id, current_user.id if current_user else None)


@router.post("/{post_id}")
def toggle_post_reaction(
    post_id: int,
    body: ReactionToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")

    rtype = (body.reaction_type or "like").strip().lower()
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
