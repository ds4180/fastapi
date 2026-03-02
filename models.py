from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, UniqueConstraint, Boolean, Table, JSON
from sqlalchemy.orm import relationship, backref 
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from database import Base

# --- Legacy v0 Models (Keep as is) ---
question_read_user = Table(
    'question_read_user',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('question_id', Integer, ForeignKey('question.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    real_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    
    # Relationships
    questions = relationship("Question", back_populates="user")
    answers = relationship("Answer", back_populates="user")
    dayoffs = relationship("DayOff", back_populates="user")
    
    # CMS v1 Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    read_histories = relationship("PostRead", back_populates="user")

    @property
    def rank(self):
        """프로필에서 rank_level을 가져오거나 기본값(0) 반환"""
        return self.profile.rank_level if self.profile else 0

    @property
    def role(self):
        """계산된 Role 문자열 반환 (BoardConfig의 JSON 키와 매칭용)"""
        if self.rank == 0:
            return "ROLE_DRIVER"
        if self.rank == 3:
            return "ROLE_ADMIN"
        return f"ROLE_STAFF_L{self.rank}"

    def get_scope(self, board_config, action="read"):
        """게시판 설정에서 나의 권한 범위(OWN, GLOBAL, NONE)를 조회"""
        perms = board_config.perm_read if action == "read" else board_config.perm_write
        if not perms:
            return "NONE"
        return perms.get(self.role, "NONE")

class UserProfile(Base):
    """사용자 업무 상세 정보 및 권한 레벨 관리 (1:1 relationship with User)"""
    __tablename__ = "user_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    rank_level = Column(Integer, default=0)       # 0:운전원, 1:실무, 2:관리, 3:최고관리
    is_active = Column(Boolean, default=True)
    employee_no = Column(String, nullable=True)    # 사번
    resident_no = Column(String, nullable=True)    # 주민번호 (양방향 암호화 필요)
    joined_date = Column(Date, nullable=True)
    bank_name = Column(String, nullable=True)
    account_no = Column(String, nullable=True)
    admin_memo = Column(Text, nullable=True)

    user = relationship("User", back_populates="profile")

class Question(Base):
    __tablename__ ="question"

    id = Column(Integer, primary_key=True)
    subject = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    modify_date = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)
    read_users = relationship("User", secondary=question_read_user, backref="read_questions")
    reactions = relationship("QuestionReaction", back_populates="question", cascade="all, delete-orphan")
    images = relationship("QuestionImage", back_populates="question", cascade="all, delete-orphan")

class QuestionImage(Base) :
    __tablename__ = "question_image"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    thumbnail_filename = Column(String, nullable=True)
    question_id = Column(Integer, ForeignKey('question.id'))

    question = relationship("Question", back_populates="images")

class Answer(Base):
    __tablename__ = "answer"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    question_id = Column(Integer, ForeignKey('question.id'))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    question = relationship("Question", back_populates="answers")
    user = relationship("User", back_populates="answers")
    modify_date = Column(DateTime, nullable=True)

class DayOff(Base):
    __tablename__ = "dayoff"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    category = Column(String, nullable=True)
    memo = Column(Text, nullable=True)
    create_date = Column(DateTime, nullable=False)
    
    user = relationship("User", back_populates="dayoffs")

    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_user_dayoff_date'),
    )

class QuestionReaction(Base):
    __tablename__ = 'question_reaction'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    question_id = Column(Integer, ForeignKey('question.id'), primary_key=True)
    reaction_type = Column(String, nullable=False) # 'like', 'dislike', 'soso'

    question = relationship("Question", back_populates="reactions")

class PushSubscription(Base):
    __tablename__ = "push_subscription"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # 알림을 받는 유저
    endpoint = Column(String, unique=True, nullable=False) # 푸시 서버 주소 (중복 허용 안함)
    p256dh = Column(String, nullable=False) # 브라우저 공개키
    auth = Column(String, nullable=False) # 인증 시크릿
    
    user = relationship("User", backref="push_subscriptions")

class Alert(Base):
    __tablename__ = "alert"

    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    level = Column(Integer, default=1)
    style = Column(String, default="info")
    position = Column(String, default="top")
    route = Column(String, nullable=True)
    redirect_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    target_users = Column(Text, nullable=True)
    confirm_text = Column(String, default="확인하였습니다")
    reset_sec = Column(Integer, default=0)
    create_date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", backref="created_alerts")

class UserSession(Base):
    __tablename__ = "user_session"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_key = Column(String, unique=True, nullable=False, index=True)
    device_category = Column(String, nullable=False, index=True)
    status = Column(String, default="ACTIVE", index=True)
    device_name = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    login_at = Column(DateTime, default=datetime.now, index=True)
    logout_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", backref="sessions")

# --- CMS v1 Models (New Construction) ---

# Table-based M2M: Tags (Simple mapping)
post_tag = Table(
    'post_tag',
    Base.metadata,
    Column('post_id', Integer, ForeignKey('post.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tag.id'), primary_key=True)
)

class BoardConfig(Base):
    """게시판 설정: CMS의 설계도"""
    __tablename__ = "board_config"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False, index=True) # URL 경로
    name = Column(String, nullable=False)                         # 보드 명칭
    description = Column(String, nullable=True)                  
    layout_type = Column(String, default="list")                 # list, gallery, split_view, landing
    items_per_page = Column(Integer, default=10)
    
    # 동적 필드 및 모듈 옵션 (JSONB)
    fields_def = Column(JSONB, default=list)                     # 커스텀 필드 정의
    options = Column(JSONB, default=dict)                        # 기능 스위치 (comment, push, ws 등)
    
    # 권한 설정 (JSONB)
    perm_read = Column(JSONB, default=dict)                      # 읽기 권한
    perm_write = Column(JSONB, default=dict)                     # 쓰기 권한
    
    is_active = Column(Boolean, default=True)
    create_date = Column(DateTime, default=datetime.now)
    
    posts = relationship("Post", back_populates="board")

class Post(Base):
    """통합 콘텐츠: CMS의 모든 글/페이지 본체"""
    __tablename__ = "post"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board_config.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    title = Column(String, nullable=False)
    content_json = Column(JSONB, nullable=False)                 # TipTap JSON 본문
    extra_data = Column(JSONB, default=dict)                     # 보드별 특수 데이터
    
    status = Column(String, default="published")                 # published, draft, private, deleted
    view_count = Column(Integer, default=0)
    create_date = Column(DateTime, default=datetime.now)
    modify_date = Column(DateTime, nullable=True)
    
    # Relationships
    board = relationship("BoardConfig", back_populates="posts")
    user = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=post_tag, backref="posts")
    read_histories = relationship("PostRead", back_populates="post", cascade="all, delete-orphan")

class Comment(Base):
    """통합 댓글: CMS 모든 포스트의 댓글"""
    __tablename__ = "comment"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("post.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("comment.id"), nullable=True) # 대댓글용
    
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    modify_date = Column(DateTime, nullable=True)
    
    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    replies = relationship("Comment", backref="parent", remote_side=[id])

class PostRead(Base):
    """클래스형 M2M: 읽음 이력 및 조회 통계"""
    __tablename__ = "post_read"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("post.id"), nullable=False)
    
    first_read_at = Column(DateTime, default=datetime.now)
    last_read_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    read_count = Column(Integer, default=1)
    device_category = Column(String, nullable=True)              # MOBILE / WORKSPACE

    user = relationship("User", back_populates="read_histories")
    post = relationship("Post", back_populates="read_histories")

    __table_args__ = (
        UniqueConstraint('user_id', 'post_id', name='uq_user_post_read'),
    )

class Tag(Base):
    """태그 마스터: 분류용 #태그 사전"""
    __tablename__ = "tag"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, default="#6c757d")                    # UI용 색상

class Menu(Base):
    """메뉴 관리: 사이트 네비게이션 트리"""
    __tablename__ = "menu"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("menu.id"), nullable=True)
    title = Column(String, nullable=False)
    icon_name = Column(String, nullable=True)                    # Iconify 아이콘 문자열
    icon_color = Column(String, nullable=True)
    
    link_type = Column(String, default="BOARD")                  # BOARD, PAGE, URL, DIVIDER
    board_id = Column(Integer, ForeignKey("board_config.id"), nullable=True)
    page_id = Column(Integer, ForeignKey("post.id"), nullable=True)
    external_url = Column(String, nullable=True)
    
    order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)
    min_rank = Column(Integer, default=0)                        # 노출 최소 권한 (0~3)

    sub_menus = relationship("Menu", backref=backref("parent", remote_side=[id]), cascade="all, delete-orphan")

    