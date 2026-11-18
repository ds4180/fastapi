from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Post, PostRead, User
from core.deps import get_current_user_optional
from domain.user.user_router import get_current_user

router = APIRouter(
    prefix="/v1/read-receipt",
    tags=["read_receipt"],
)


class ReadMarkRequest(BaseModel):
    device_category: Optional[str] = None


def _build_read_summary(db: Session, post_id: int, user_id: Optional[int]) -> dict:
    reads = (
        db.query(PostRead, User)
        .join(User, PostRead.user_id == User.id)
        .filter(PostRead.post_id == post_id)
        .order_by(PostRead.first_read_at.asc())
        .all()
    )

    read_user_ids = {r.user_id for r, _ in reads}
    readers = [
        {
            "user_id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "display_name": u.real_name or u.username,
            "first_read_at": r.first_read_at,
            "last_read_at": r.last_read_at,
            "read_count": r.read_count,
        }
        for r, u in reads
    ]

    unread_users_q = db.query(User)
    if read_user_ids:
        unread_users_q = unread_users_q.filter(~User.id.in_(read_user_ids))
    unread_users = [
        {
            "user_id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "display_name": u.real_name or u.username,
        }
        for u in unread_users_q.order_by(User.id.asc()).all()
    ]

    my_read = next((x for x in readers if x["user_id"] == user_id), None) if user_id is not None else None

    return {
        "post_id": post_id,
        "read_count": len(readers),
        "unread_count": len(unread_users),
        "readers": readers,
        "unread_users": unread_users,
        "my_read": my_read,
    }


@router.get("/{post_id}")
def get_read_receipts(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return _build_read_summary(db, post_id, current_user.id if current_user else None)


@router.post("/{post_id}")
def mark_post_read(
    post_id: int,
    body: Optional[ReadMarkRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")

    now = datetime.now()
    existing = (
        db.query(PostRead)
        .filter(PostRead.post_id == post_id, PostRead.user_id == current_user.id)
        .first()
    )

    if existing:
        existing.last_read_at = now
        existing.read_count = (existing.read_count or 1) + 1
        if body and body.device_category:
            existing.device_category = body.device_category
    else:
        db.add(
            PostRead(
                user_id=current_user.id,
                post_id=post_id,
                first_read_at=now,
                last_read_at=now,
                read_count=1,
                device_category=body.device_category if body else None,
            )
        )

    db.commit()
    return _build_read_summary(db, post_id, current_user.id)
