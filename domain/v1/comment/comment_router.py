from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import User, Comment, Post
from domain.v1.comment import comment_schema, comment_crud
from domain.user.user_router import get_current_user

router = APIRouter(
    prefix="/v1/comment",
    tags=["comment"]
)

@router.get("/{post_id}", response_model=List[comment_schema.Comment])
def get_comments(post_id: int, db: Session = Depends(get_db)):
    """특정 게시물의 댓글 목록 조회 (대댓글 트리 구조 포함)"""
    return comment_crud.get_comments_by_post(db, post_id=post_id)

@router.post("/{post_id}", response_model=comment_schema.Comment)
def create_comment(
    post_id: int,
    comment_in: comment_schema.CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """댓글 작성 (Post 존재 확인 후 생성)"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    
    return comment_crud.create_comment(db, post_id=post_id, user_id=current_user.id, comment_in=comment_in)

@router.put("/{comment_id}", response_model=comment_schema.Comment)
def update_comment(
    comment_id: int,
    comment_in: comment_schema.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """댓글 수정 (본인 또는 관리자 확인)"""
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    
    # 권한 체크: 작성자 본인이거나 Rank 4 이상(최고 관리자)
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if db_comment.user_id != current_user.id and user_rank < 4:
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다.")
        
    return comment_crud.update_comment(db, db_comment=db_comment, comment_in=comment_in)

@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """댓글 삭제 (본인 또는 관리자 확인)"""
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    
    # 권한 체크: 작성자 본인이거나 Rank 4 이상(최고 관리자)
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if db_comment.user_id != current_user.id and user_rank < 4:
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")
        
    comment_crud.delete_comment(db, db_comment=db_comment)
    return {"message": "success"}
