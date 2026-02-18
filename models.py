from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, UniqueConstraint, Boolean, Table
from sqlalchemy.orm import relationship 

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

    user = relationship("User", backref="reactions")
    question = relationship("Question", back_populates="reactions")