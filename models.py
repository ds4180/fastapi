from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, UniqueConstraint, Boolean, Table, JSON, Index, and_
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from database import Base

# --- M2M 및 관계 테이블 ---

question_read_user = Table(
    'question_read_user',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('question_id', Integer, ForeignKey('question.id'), primary_key=True)
)

post_tag = Table(
    'post_tag',
    Base.metadata,
    Column('post_id', Integer, ForeignKey('post.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tag.id'), primary_key=True)
)

# --- Core Models (User & Session) ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    real_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    questions = relationship("Question", back_populates="user")
    answers = relationship("Answer", back_populates="user")
    dayoffs = relationship("DayOff", back_populates="user")
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    read_histories = relationship("PostRead", back_populates="user")

    def rank(self):
        return self.profile.rank_level if self.profile else 0

    @property
    def role(self):
        r = self.rank()
        if r == 0: return "ROLE_GUEST"
        if r == 4: return "ROLE_ADMIN"
        return f"ROLE_STAFF_L{r}"

class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    rank_level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    employee_no = Column(String, nullable=True)
    resident_no = Column(String, nullable=True)
    joined_date = Column(Date, nullable=True)
    bank_name = Column(String, nullable=True)
    account_no = Column(String, nullable=True)
    admin_memo = Column(Text, nullable=True)
    user = relationship("User", back_populates="profile")

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

# --- CMS Core ---

class SystemConfig(Base):
    __tablename__ = "system_config"
    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    description = Column(String, nullable=True)
    updated_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class AppRegistry(Base):
    __tablename__ = "app_registry"
    app_id = Column(String, primary_key=True, index=True) # 앱 고유 식별자
    name = Column(String, nullable=False) # 앱 이름
    title = Column(String, nullable=True) # 공식 명칭 (UI 표시용)
    description = Column(Text, nullable=True) # 타이틀 하단 요약 설명
    
    # 추상화 및 경로 메타데이터
    app_type = Column(String, default="INSTANCE") # INSTANCE, STATIC, SYSTEM
    frontend_route = Column(String, nullable=True) # Svelte 라우트 경로
    main_component = Column(String, nullable=True) # 메인 컴포넌트 파일명 (Dynamic Import용)
    icon_default = Column(String, nullable=True) # 기본 아이콘
    
    # 보안 주권 설정 (v1.3)
    min_read_rank = Column(Integer, default=0) # 읽기/진입 최소 권한
    min_write_rank = Column(Integer, default=2) # 쓰기/행위 최소 권한
    admin_ids = Column(JSONB, default=list) # 해당 앱 자치 관리자 리스트 ([user_id, ...])
    
    config_schema = Column(JSONB, default=dict) # 앱 인스턴스 전용 설정 스키마 (Meta Service)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class ServiceRegistry(Base):
    """서비스 앱 대분류 (댓글, 추천, 업로드 등)"""
    __tablename__ = "service_registry"
    id = Column(String, primary_key=True) # "comment", "upload"
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

class ServiceEngine(Base):
    """실제 작동하는 레고 엔진 (v1, v2 등)"""
    __tablename__ = "service_engine"
    id = Column(String, primary_key=True) # "basic_comment_v1"
    registry_id = Column(String, ForeignKey("service_registry.id"), nullable=False)
    version = Column(String, nullable=False, default="1.0.0")
    
    frontend_plugin = Column(String, nullable=True) # 렌더링할 Svelte 컴포넌트 경로
    config_schema = Column(JSONB, default=dict) # 엔진별 필수 설정 스키마
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

class ServiceBinding(Base):
    """앱 인스턴스와 레고 엔진의 연결 (접착제)"""
    __tablename__ = "service_binding"
    id = Column(Integer, primary_key=True)
    target_app = Column(String, index=True) # "board", "dashboard"
    target_id = Column(Integer, index=True) # 인스턴스 ID (board_id 등)
    engine_id = Column(String, ForeignKey("service_engine.id"), nullable=False)
    
    # 개별 바인딩 커스텀 설정
    custom_config = Column(JSONB, default=dict) # {"grid_span": 2, "color": "blue"}
    min_write_rank = Column(Integer, nullable=True) # 엔진별 행위 권한 (null이면 앱설정 상속)
    order = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

class Menu(Base):
    __tablename__ = "menu"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("menu.id"), nullable=True)
    title = Column(String, nullable=False)
    icon_name = Column(String, nullable=True)
    icon_color = Column(String, nullable=True)
    link_type = Column(String, default="URL") # URL, APP, PAGE, DIVIDER
    app_id = Column(String, ForeignKey("app_registry.app_id"), nullable=True) # 연결된 App 엔진 ID
    app_instance_id = Column(Integer, nullable=True) # 해당 App의 인스턴스 ID (예: board_id)
    page_id = Column(Integer, nullable=True)
    external_url = Column(String, nullable=True)
    order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)
    min_rank = Column(Integer, default=0)
    sub_menus = relationship("Menu", backref=backref("parent", remote_side=[id]), cascade="all, delete-orphan")

# --- CMS Board & Post ---

class BoardConfig(Base):
    __tablename__ = "board_config"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    layout_type = Column(String, default="list")
    
    # 레거시와 호환성 유지를 위해 필드 보존
    items_per_page = Column(Integer, default=10)
    fields_def = Column(JSONB, default=list) 
    options = Column(JSONB, default=dict)
    
    perm_read = Column(JSONB, default={"ROLE_GUEST": "GLOBAL"})
    perm_write = Column(JSONB, default={"ROLE_USER": "GLOBAL"})
    is_active = Column(Boolean, default=True)
    create_date = Column(DateTime, nullable=False, default=datetime.now)

    # Post 모델과의 양방향 관계 설정
    posts = relationship("Post", back_populates="board", cascade="all, delete-orphan")

class Post(Base):
    __tablename__ = "post"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board_config.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    content_json = Column(JSONB, nullable=False) # TipTap JSON
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
    __tablename__ = "post_reaction"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    post_id = Column(Integer, ForeignKey("post.id"), primary_key=True)
    reaction_type = Column(String, nullable=False) # 'like', 'dislike', 'soso'
    post = relationship("Post", back_populates="reactions")
    user = relationship("User", backref="post_reactions")

class Tag(Base):
    __tablename__ = "tag"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=True)

class Comment(Base):
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

# --- Legacy Question/Answer ---

class Question(Base):
    __tablename__ ="question"
    id = Column(Integer, primary_key=True)
    subject = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    modify_date = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    read_users = relationship("User", secondary=question_read_user, backref="read_questions")
    reactions = relationship("QuestionReaction", back_populates="question", cascade="all, delete-orphan")
    images = relationship("QuestionImage", back_populates="question", cascade="all, delete-orphan")

class Answer(Base):
    __tablename__ = "answer"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("question.id"))
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 중복된 backref 제거 후 back_populates 사용
    question = relationship("Question", back_populates="answers")
    user = relationship("User", back_populates="answers")

class QuestionReaction(Base):
    __tablename__ = "question_reaction"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    question_id = Column(Integer, ForeignKey("question.id"), primary_key=True)
    reaction_type = Column(String, nullable=False)
    question = relationship("Question", back_populates="reactions")

class QuestionImage(Base):
    __tablename__ = "question_image"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    question_id = Column(Integer, ForeignKey("question.id"))
    thumbnail_filename = Column(String, nullable=True)
    question = relationship("Question", back_populates="images")

# --- Others ---

class DayOff(Base):
    __tablename__ = "dayoff"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, default="REQUESTED")
    memo = Column(Text, nullable=True)
    
    # 그룹화 및 Soft Delete 필드 추가
    group_id = Column(String, nullable=True, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)
    create_date = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('ix_dayoff_user_date_active', 'user_id', 'date', 
              unique=True, postgresql_where=(is_deleted == False)),
    )

    user = relationship("User", back_populates="dayoffs")

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
    target_users = Column(String, nullable=True) # 특정 사용자 대상 (쉼표 구분 또는 JSON)
    confirm_text = Column(String, default="확인하였습니다")
    reset_sec = Column(Integer, default=0)
    create_date = Column(DateTime, nullable=False, default=datetime.now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", backref="created_alerts")

# --- Page Engine (v1.0) ---

class Page(Base):
    """독립형 고정 컨텐츠 페이지 엔진 모델"""
    __tablename__ = "page"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False) # URL 주소용 식별자
    title = Column(String, nullable=False)                         # 페이지 제목
    content = Column(Text, nullable=True)                          # 일반 텍스트/HTML 본문
    content_json = Column(JSONB, nullable=False)                   # TipTap 에디터 데이터
    
    status = Column(String, default="DRAFT")                       # DRAFT, PUBLISHED
    is_active = Column(Boolean, default=True)                      # 활성 여부
    min_rank = Column(Integer, default=0)                          # 열람 가능한 최소 등급
    
    # [v1.0.4] 리다이렉트 기능 추가
    redirect_url = Column(String, nullable=True)
    
    # [표준] Soft Delete 정책 반영
    is_deleted = Column(Boolean, default=False, nullable=False)
    delete_date = Column(DateTime, nullable=True)
    
    published_at = Column(DateTime, nullable=False, default=datetime.now) # 게시 시작 시각
    expired_at = Column(DateTime, nullable=True)                         # 게시 종료 시각 (선택)
    
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class PushSubscription(Base):
    __tablename__ = "push_subscription"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
