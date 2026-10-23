"""
============================================================================
[Q&A 질문/답변 레거시 모델 (models/question.py)]
============================================================================

💡 이 파일의 역할:
질문(Question), 답변(Answer), 질문 반응(QuestionReaction), 첨부 이미지(QuestionImage),
및 열람 사용자 다대다 조인 테이블(question_read_user)을 정의합니다.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from models.base import Base

# --- N:M 다대다 조인 테이블 ---
question_read_user = Table(
    'question_read_user',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('question_id', Integer, ForeignKey('question.id'), primary_key=True)
)


class Question(Base):
    """Q&A 질문 본문 모델"""
    __tablename__ = "question"

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
    """Q&A 답변 모델"""
    __tablename__ = "answer"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("question.id"))
    content = Column(Text, nullable=False)
    create_date = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    question = relationship("Question", back_populates="answers")
    user = relationship("User", back_populates="answers")


class QuestionReaction(Base):
    """Q&A 질문 반응 모델"""
    __tablename__ = "question_reaction"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    question_id = Column(Integer, ForeignKey("question.id"), primary_key=True)
    reaction_type = Column(String, nullable=False)

    question = relationship("Question", back_populates="reactions")


class QuestionImage(Base):
    """Q&A 질문 첨부 이미지 모델"""
    __tablename__ = "question_image"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    question_id = Column(Integer, ForeignKey("question.id"))
    thumbnail_filename = Column(String, nullable=True)

    question = relationship("Question", back_populates="images")
