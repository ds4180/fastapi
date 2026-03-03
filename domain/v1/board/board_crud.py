from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from models import Post, BoardConfig, User, PostRead, Comment, PostReaction
from domain.v1.board.board_schema import PostCreate, PostUpdate
from typing import List, Optional

def get_post_list(db: Session, board_id: int, skip: int = 0, limit: int = 10, user: User = None, keyword: str = ""):
    query = db.query(Post).filter(
        Post.board_id == board_id,
        Post.is_deleted == False
    )

    if keyword:
        search = f"%%{keyword}%%"
        query = query.outerjoin(User).filter(
            or_(
                Post.title.ilike(search),
                Post.content.ilike(search),
                User.username.ilike(search),
                User.real_name.ilike(search)
            )
        ).distinct()

    total = query.count()
    posts = query.order_by(Post.create_date.desc()).offset(skip).limit(limit).all()

    result_posts = []
    for post in posts:
        post_data = {
            "id": post.id,
            "title": post.title,
            "content": post.content, # 추가
            "content_json": post.content_json,
            "extra_data": post.extra_data,
            "status": post.status,
            "view_count": post.view_count,
            "create_date": post.create_date,
            "user_name": post.user.real_name or post.user.username if post.user else "탈퇴한 사용자",
            "is_read": False,
            "like_count": len(post.reactions),
            "comment_count": len(post.comments)
        }
        
        if user:
            is_read = db.query(PostRead).filter(
                PostRead.post_id == post.id,
                PostRead.user_id == user.id
            ).first()
            post_data["is_read"] = True if is_read else False

        result_posts.append(post_data)

    return total, result_posts

def create_post(db: Session, board_id: int, user_id: int, post_in: PostCreate):
    """새 게시물 생성 (TipTap JSON 및 Extra Data 지원)"""
    db_post = Post(
        board_id=board_id,
        user_id=user_id,
        title=post_in.title,
        content=post_in.content,
        content_json=post_in.content_json,
        extra_data=post_in.extra_data,
        status=post_in.status,
        create_date=datetime.now()
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def get_post_detail(db: Session, post_id: int):
    """게시물 상세 조회"""
    return db.query(Post).filter(Post.id == post_id, Post.is_deleted == False).first()

def update_post(db: Session, db_post: Post, post_in: PostUpdate):
    """게시물 수정"""
    update_data = post_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_post, key, value)
    
    db_post.modify_date = datetime.now()
    db.commit()
    db.refresh(db_post)
    return db_post

def delete_post(db: Session, db_post: Post):
    """게시물 삭제 (Soft Delete)"""
    db_post.is_deleted = True
    db_post.delete_date = datetime.now()
    db.commit()
    return True
