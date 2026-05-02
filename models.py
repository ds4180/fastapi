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

class ServiceApp(Base):
    """원자적 기능 단위 (댓글, 설문 등)"""
    __tablename__ = "service_app"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    engine_id = Column(String, ForeignKey("service_engine.id"), nullable=False)
    config = Column(JSONB, default=dict)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

class ServiceInstance(Base):
    """조합된 서비스 앱 덩어리 (조립 설명서)"""
    __tablename__ = "service_instance"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    # 조립될 서비스 앱 ID들이 순서대로 담긴 리스트 (예: [101, 102, 105])
    service_app_ids = Column(JSONB, default=list) 
    
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
    sub_menus = relationship("Menu", backref=backref("parent", remote_side=[id]), cascade="all, delete-orphan", order_by="Menu.order")

# --- CMS Board & Post ---

class BoardConfig(Base):
    __tablename__ = "board_config"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    layout_type = Column(String, default="list")
    service_instance_id = Column(Integer, ForeignKey("service_instance.id"), nullable=True) # 덩어리 참조
    
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

class MediaAsset(Base):
    """시스템 전역 미디어 자산 관리 모델 (Production-ready)"""
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 계층 및 권한 설정
    access_level = Column(String(20), default="PUBLIC") # PUBLIC, PROTECTED, PRIVATE, SYSTEM
    app_id = Column(String(50), index=True)             # 'board', 'profile', 'admin' 등
    target_id = Column(String(100), index=True)         # 연결된 대상의 식별자
    
    # 파일 물리 정보
    original_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)     # 실제 저장 상대 경로
    thumbnail_path = Column(String(500), nullable=True)  # 기본 썸네일 경로 (레거시 대응용)
    
    # 상세 메타데이터 (이미지 규격, 다중 썸네일 등)
    # { "width": 1024, "height": 768, "thumbs": {"sm": "...", "md": "...", "lg": "..."} }
    meta_info = Column(JSONB, default=dict)
    
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    category = Column(String(20))                       # 'image', 'document', 'archive'
    
    # 상태 관리
    is_deleted = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="media_assets")

class SystemTask(Base):
    """
    [시스템 자율 신경계] 지능형 범용 비동기 태스크 및 스케줄러 엔진 모델
    이 테이블은 시스템의 모든 비동기 작업(파일 처리, 메일 발송, 예약 게시 등)을 관리하는 '작업 일지'입니다.
    """
    __tablename__ = "system_tasks"

    # --- 1. 기본 식별 정보 ---
    id = Column(Integer, primary_key=True)
    task_type = Column(String(50), nullable=False, index=True) # 어떤 종류의 일인가? (예: 'MEDIA_GC', 'MAIL_SEND')
    payload = Column(JSONB, default=dict)                      # 일에 필요한 재료들 (JSON 형식)
    result = Column(JSONB, default=dict)                       # 일이 끝난 후 남기는 결과물

    # --- 2. 실행 제어 및 연쇄 작업 (Chaining) ---
    priority = Column(Integer, default=5, index=True)          # 급한 일인가? (1: 매우급함, 10: 여유있음)
    unique_key = Column(String(100), unique=True)              # 똑같은 일이 중복해서 생기는 것 방지
    parent_id = Column(Integer, ForeignKey("system_tasks.id")) # 이 일의 '엄마'가 있는가? (부모-자식 연쇄 작업)
    on_parent_failure = Column(String(20), default="CANCEL")   # 엄마가 실패하면 이 일은 어떻게 할까? (취소 또는 계속)
    
    # --- 3. 스케줄링 및 자생적 반복 (Scheduler) ---
    scheduled_at = Column(DateTime, default=datetime.now, index=True) # 언제 실행할 예정인가? (미래 시점 예약 가능)
    cron_expression = Column(String(50), nullable=True)        # "매일 새벽 3시"처럼 반복해서 할 일인가? (Cron 표현식)
    repeat_interval = Column(Integer, nullable=True)          # "60초마다"처럼 주기적으로 반복할 일인가? (초 단위)
    
    # --- 4. 현재 진행 상태 (Status) ---
    status = Column(String(20), default="PENDING", index=True) # 현재 상태 (대기중, 실행중, 성공, 실패, 취소 등)
    worker_id = Column(String(50), nullable=True)              # 지금 어떤 서버(작업자)가 이 일을 하고 있는가?
    progress_pct = Column(Integer, default=0)                  # 일이 얼마나 진행되었나? (0% ~ 100%)
    
    # --- 5. 안정성 및 에러 추적 ---
    retry_count = Column(Integer, default=0)                   # 실패해서 다시 시도한 횟수
    max_retries = Column(Integer, default=3)                   # 최대 몇 번까지 다시 해볼까?
    expires_at = Column(DateTime, nullable=True)               # 이 시간이 지나면 너무 늦었으니 일을 취소함
    timeout_sec = Column(Integer, default=300)                 # 일을 시작하고 몇 초 안에 안 끝나면 강제 중단할까?
    error_log = Column(Text, nullable=True)                    # 실패했다면 그 이유(에러 메시지)는 무엇인가?
    tags = Column(JSONB, default=list)                         # 나중에 관리자가 검색하기 편하게 붙이는 꼬리표
    
    # --- 6. 생성 맥락 및 로그 ---
    created_by = Column(Integer, ForeignKey("users.id"))       # 누가 이 일을 시켰는가?
    correlation_id = Column(String(100), index=True)           # 이 일을 만든 웹 요청이 무엇인지 추적하는 ID
    
    created_at = Column(DateTime, default=datetime.now)        # 일지가 처음 작성된 시각
    started_at = Column(DateTime, nullable=True)               # 실제로 일을 시작한 시각
    completed_at = Column(DateTime, nullable=True)             # 일이 완전히 끝난 시각

    # 자기 자신과의 관계 설정 (연쇄 작업 추적용)
    parent = relationship("SystemTask", remote_side=[id], backref="children")

class PushSubscription(Base):
    __tablename__ = "push_subscription"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
