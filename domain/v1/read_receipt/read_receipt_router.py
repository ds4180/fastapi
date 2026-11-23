from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import User
from core.deps import get_current_user, get_current_user_optional
from domain.v1.read_receipt import read_receipt_service

router = APIRouter(
    prefix="/v1/read-receipt",
    tags=["read_receipt"],
)


class ReadMarkRequest(BaseModel):
    device_category: Optional[str] = None


@router.get("/{post_id}")
def get_read_receipts(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    return read_receipt_service.get_read_receipt_summary(db, post_id=post_id, current_user=current_user)


@router.post("/{post_id}")
def mark_post_read(
    post_id: int,
    body: Optional[ReadMarkRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return read_receipt_service.mark_post_read(
        db,
        post_id=post_id,
        device_category=body.device_category if body else None,
        current_user=current_user,
    )
