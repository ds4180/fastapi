from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import User
from domain.v1.comment import comment_schema, comment_service
from core.deps import get_current_user, get_current_user_optional

router = APIRouter(
    prefix="/v1/comment",
    tags=["comment"],
)


@router.get("/{post_id}", response_model=List[comment_schema.Comment])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """특정 게시물의 댓글 목록 조회 (대댓글 트리 구조 포함)"""
    return comment_service.list_post_comments(db, post_id=post_id, current_user=current_user)


@router.post("/{post_id}", response_model=comment_schema.Comment)
def create_comment(
    post_id: int,
    comment_in: comment_schema.CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """댓글 작성 (Post 존재 및 서비스 권한 확인 후 생성)"""
    return comment_service.create_post_comment(
        db, post_id=post_id, comment_in=comment_in, current_user=current_user
    )


@router.put("/{comment_id}", response_model=comment_schema.Comment)
def update_comment(
    comment_id: int,
    comment_in: comment_schema.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """댓글 수정 (본인 또는 관리자 확인)"""
    return comment_service.update_post_comment(
        db, comment_id=comment_id, comment_in=comment_in, current_user=current_user
    )


@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """댓글 삭제 (본인 또는 관리자 확인)"""
    return comment_service.delete_post_comment(db, comment_id=comment_id, current_user=current_user)
