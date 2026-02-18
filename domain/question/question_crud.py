from datetime import datetime

from domain.question.question_schema import QuestionCreate, QuestionUpdate

from models import Question, User, QuestionReaction
from sqlalchemy.orm import Session


def get_question_list(db: Session, skip: int = 0, limit: int = 10, user: User = None):
    _question_list = db.query(Question)\
        .filter(Question.is_deleted == False)\
        .order_by(Question.create_date.desc())

    total = _question_list.count()
    question_list = _question_list.offset(skip).limit(limit).all()

    if user:
        for question in question_list:
            question.is_read = user in question.read_users

    return total, question_list  # (전체 건수, 페이징 적용된 질문 목록)

    # question_list = db.query(Question).order_by(Question.create_date.desc()).all()
    # return question_list --페이징 하면서 업그레이드 시킴.

def get_question(db: Session, question_id: int, user: User = None):
    question = db.query(Question).filter(Question.id == question_id, Question.is_deleted == False).first()
    
    if question:
        # 읽음 정보 집계
        question.read_count = len(question.read_users)
        if user:
            question.is_read = user in question.read_users
        
        # 반응 정보 집계
        question.like_count = db.query(QuestionReaction).filter(
            QuestionReaction.question_id == question_id, 
            QuestionReaction.reaction_type == 'like'
        ).count()
        question.dislike_count = db.query(QuestionReaction).filter(
            QuestionReaction.question_id == question_id, 
            QuestionReaction.reaction_type == 'dislike'
        ).count()
        question.soso_count = db.query(QuestionReaction).filter(
            QuestionReaction.question_id == question_id, 
            QuestionReaction.reaction_type == 'soso'
        ).count()
        
        if user:
            reaction = db.query(QuestionReaction).filter(
                QuestionReaction.question_id == question_id,
                QuestionReaction.user_id == user.id
            ).first()
            question.my_reaction = reaction.reaction_type if reaction else None
            
    return question

def create_question(db:Session, question_create:QuestionCreate, user:User):
    db_question = Question(subject=question_create.subject,
                           content=question_create.content,
                           create_date=datetime.now(),
                           user=user)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

def add_read_user(db: Session, db_question: Question, user: User):
    if user not in db_question.read_users:
        db_question.read_users.append(user)
        db.commit()

def remove_read_user(db: Session, db_question: Question, user: User):
    if user in db_question.read_users:
        db_question.read_users.remove(user)
        db.commit()

def toggle_reaction(db: Session, db_question: Question, user: User, reaction_type: str):
    existing_reaction = db.query(QuestionReaction).filter(
        QuestionReaction.question_id == db_question.id,
        QuestionReaction.user_id == user.id
    ).first()

    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # 동일한 반응이면 취소 (삭제)
            db.delete(existing_reaction)
        else:
            # 다른 반응이면 업데이트
            existing_reaction.reaction_type = reaction_type
    else:
        # 반응이 없으면 생성
        new_reaction = QuestionReaction(
            user_id=user.id,
            question_id=db_question.id,
            reaction_type=reaction_type
        )
        db.add(new_reaction)
    
    db.commit()

def delete_question(db: Session, db_question: Question):
    db_question.is_deleted = True
    db_question.delete_date = datetime.now()
    db.add(db_question)
    db.commit()

def update_question(db:Session, db_question:Question, question_update:QuestionUpdate):
    db_question.subject = question_update.subject
    db_question.content = question_update.content
    db_question.modify_date = datetime.now()
    db.add(db_question)
    db.commit()
    
    db.refresh(db_question)
    return db_question