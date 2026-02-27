from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, UniqueConstraint, Boolean, Table
from sqlalchemy.orm import relationship 
from datetime import datetime

from database import Base

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
    questions = relationship("Question", back_populates="user")
    answers = relationship("Answer", back_populates="user")
    dayoffs = relationship("DayOff", back_populates="user")

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
    """
    업무 지시 및 알림 테이블.
    단순 팝업부터 Level 4(강제 정독) 공지까지 관리합니다.
    """
    __tablename__ = "alert"

    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False) # "배차 확인 요망" 등 2~3줄의 핵심 지시
    level = Column(Integer, default=1)     # 1(일반 팝업) ~ 4(강제 확인 모달)
    style = Column(String, default="info")     # info, success, warning, danger
    position = Column(String, default="top")  # top(상단), bottom(하단)
    route = Column(String, nullable=True)  # 노출 특정 경로 (비어있으면 전역 노출)
    redirect_url = Column(String, nullable=True) # 확인 클릭 시 강제 이동할 주소 (공지 본문 등)
    is_active = Column(Boolean, default=True)    # 적용/중지 수동 제어
    start_date = Column(DateTime, nullable=True) # 예약 시작 시점
    end_date = Column(DateTime, nullable=True)   # 노출 자동 종료 시점
    target_users = Column(Text, nullable=True)   # 대상 필터 (JSON 형식 등으로 저장)
    confirm_text = Column(String, default="확인하였습니다") # 버튼 문구
    reset_sec = Column(Integer, default=0)       # Level 4 전용 강제 대기 초
    create_date = Column(DateTime, nullable=False) # 생성 일시
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # 작성 관리자

    user = relationship("User", backref="created_alerts")

class UserSession(Base):
    """
    접속 로그 및 세션 슬롯 관리 테이블.
    - device_category: MOBILE(폰) / WORKSPACE(PC, 패드)
    - status: ACTIVE(접속중), KICKED_OUT(밀려남), LOGGED_OUT(로그아웃)
    """
    __tablename__ = "user_session"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_key = Column(String, unique=True, nullable=False, index=True) # JWT의 JTI(고유아이디)
    device_category = Column(String, nullable=False, index=True)          # MOBILE / WORKSPACE
    status = Column(String, default="ACTIVE", index=True)                # ACTIVE, KICKED_OUT, LOGGED_OUT
    device_name = Column(String, nullable=True)                          # "iPhone 15", "Windows Chrome"
    ip_address = Column(String, nullable=True)
    login_at = Column(DateTime, default=datetime.now, index=True)
    logout_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.now, index=True)   # 좀비 세션 체크용

    user = relationship("User", backref="sessions")
    