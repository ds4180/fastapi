from datetime import datetime
from sqlalchemy.orm import Session
from models import Comment, User
from domain.v1.comment.comment_schema import CommentCreate, CommentUpdate

def get_comments_by_post(db: Session, post_id: int):
    return db.query(Comment).filter(
        Comment.post_id == post_id,
        Comment.parent_id == None
    ).order_by(Comment.create_date.asc()).all()

def create_comment(db: Session, post_id: int, user_id: int, comment_in: CommentCreate):
    db_comment = Comment(
        post_id=post_id,
        user_id=user_id,
        content=comment_in.content,
        parent_id=comment_in.parent_id,
        create_date=datetime.now()
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

def update_comment(db: Session, db_comment: Comment, comment_in: CommentUpdate):
    db_comment.content = comment_in.content
    db_comment.modify_date = datetime.now()
    db.commit()
    db.refresh(db_comment)
    return db_comment

def delete_comment(db: Session, db_comment: Comment):
    db.delete(db_comment)
    db.commit()
