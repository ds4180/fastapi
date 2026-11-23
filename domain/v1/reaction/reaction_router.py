from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import User
from core.deps import get_current_user, get_current_user_optional
from domain.v1.reaction import reaction_service

router = APIRouter(
    prefix="/v1/reaction",
    tags=["reaction"],
)


class ReactionToggleRequest(BaseModel):
    reaction_type: str = "like"


@router.get("/{post_id}")
def get_post_reactions(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    return reaction_service.get_reaction_summary(db, post_id=post_id, current_user=current_user)


@router.post("/{post_id}")
def toggle_post_reaction(
    post_id: int,
    body: ReactionToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return reaction_service.toggle_reaction(
        db, post_id=post_id, reaction_type=body.reaction_type, current_user=current_user
    )
