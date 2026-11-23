"""
============================================================================
[열람 확인 비즈니스 서비스 레이어 (domain/v1/read_receipt/read_receipt_service.py)]
============================================================================
"""

from datetime import datetime
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Post, PostRead, User
from domain.v1.admin.service_service import enforce_post_service_permission


def _get_active_post_or_404(db: Session, post_id: int) -> Post:
    post = db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    return post


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


def get_read_receipt_summary(db: Session, post_id: int, current_user: Optional[User]) -> dict:
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "read_receipt", action="read")
    return _build_read_summary(db, post_id, current_user.id if current_user else None)


def mark_post_read(
    db: Session,
    post_id: int,
    device_category: Optional[str],
    current_user: User,
) -> dict:
    post = _get_active_post_or_404(db, post_id)
    enforce_post_service_permission(db, post, current_user, "read_receipt", action="write")

    now = datetime.now()
    existing = (
        db.query(PostRead)
        .filter(PostRead.post_id == post_id, PostRead.user_id == current_user.id)
        .first()
    )

    if existing:
        existing.last_read_at = now
        existing.read_count = (existing.read_count or 1) + 1
        if device_category:
            existing.device_category = device_category
    else:
        db.add(
            PostRead(
                user_id=current_user.id,
                post_id=post_id,
                first_read_at=now,
                last_read_at=now,
                read_count=1,
                device_category=device_category,
            )
        )

    db.commit()
    return _build_read_summary(db, post_id, current_user.id)
