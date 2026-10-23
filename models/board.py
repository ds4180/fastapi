"""
============================================================================
[게시판 및 콘텐츠 관리(CMS) 모델 (models/board.py)]
============================================================================

💡 이 파일의 역할:
게시판 설정(BoardConfig), 게시글(Post), 댓글(Comment), 반응/좋아요(PostReaction),
태그(Tag), 열람 기록(PostRead) 및 다대다 조인 테이블(post_tag)을 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Table, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base

# --- N:M 다대다 조인 테이블 ---
post_tag = Table(
    'post_tag',
    Base.metadata,
    Column('post_id', Integer, ForeignKey('post.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tag.id'), primary_key=True)
)


class BoardConfig(Base):
    """게시판 설정 마스터 모델 (슬러그, 레이아웃, 권한 등)"""
    __tablename__ = "board_config"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    layout_type = Column(String, default="list")
    service_instance_id = Column(Integer, ForeignKey("service_instance.id"), nullable=True)
    
    items_per_page = Column(Integer, default=10)
    fields_def = Column(JSONB, default=list) 
    options = Column(JSONB, default=dict)
    
    perm_read = Column(JSONB, default={"ROLE_GUEST": "GLOBAL"})
    perm_write = Column(JSONB, default={"ROLE_USER": "GLOBAL"})
    is_active = Column(Boolean, default=True)
    create_date = Column(DateTime, nullable=False, default=datetime.now)

    posts = relationship("Post", back_populates="board", cascade="all, delete-orphan")


class Post(Base):
    """게시글 본문 모델 (TipTap JSON 포맷 포함)"""
    __tablename__ = "post"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board_config.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    content_json = Column(JSONB, nullable=False) # TipTap 에디터 JSON 데이터
    extra_data = Column(JSONB, default=dict)
    
    status = Column(String, default="published")
    view_count = Column(Integer, default=0)
    create_date = Column(DateTime, default=datetime.now)
    modify_date = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="posts")
    board = relationship("BoardConfig", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=post_tag, backref="posts")
    read_histories = relationship("PostRead", back_populates="post", cascade="all, delete-orphan")
    reactions = relationship("PostReaction", back_populates="post", cascade="all, delete-orphan")


class PostReaction(Base):
    """게시글 추천/비추천 반응 모델"""
    __tablename__ = "post_reaction"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    post_id = Column(Integer, ForeignKey("post.id"), primary_key=True)
    reaction_type = Column(String, nullable=False) # 'like', 'dislike', 'soso'

    post = relationship("Post", back_populates="reactions")
    user = relationship("User", backref="post_reactions")


class Tag(Base):
    """게시글 태그 모델"""
    __tablename__ = "tag"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=True)


class Comment(Base):
    """게시글 댓글 및 대댓글(계층형) 모델"""
    __tablename__ = "comment"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("post.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comment.id"), nullable=True)
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    modify_date = Column(DateTime, nullable=True)

    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    sub_comments = relationship("Comment", backref=backref("parent", remote_side=[id]), cascade="all, delete-orphan")


class PostRead(Base):
    """게시글 열람 이력 및 조회수 중복 방지 모델"""
    __tablename__ = "post_read"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("post.id"), nullable=False)
    first_read_at = Column(DateTime, default=datetime.now)
    last_read_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    read_count = Column(Integer, default=1)
    device_category = Column(String, nullable=True)

    user = relationship("User", back_populates="read_histories")
    post = relationship("Post", back_populates="read_histories")

    __table_args__ = (UniqueConstraint('user_id', 'post_id', name='uq_user_post_read'),)
