from datetime import datetime

from domain.question.question_schema import QuestionCreate, QuestionUpdate

from models import Question, User, QuestionReaction, QuestionImage
from sqlalchemy.orm import Session
from sqlalchemy import or_
from domain.fileupload import fileupload_service

def get_question_list(db: Session, skip: int = 0, limit: int = 10, user: User = None, keyword: str = ""):
    _question_list = db.query(Question)\
        .outerjoin(User)\
        .filter(Question.is_deleted == False)
    
    if keyword:
        search = f"%%{keyword}%%"
        _question_list = _question_list.filter(
            or_(
                Question.subject.ilike(search),        # 질문 제목
                Question.content.ilike(search),        # 질문 내용
                User.username.ilike(search)            # 질문 작성자
            )
        ).distinct()

    _question_list = _question_list.order_by(Question.create_date.desc())
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
    # 1. 임시 파일을 최종 경로로 이동 및 썸네일 생성
    final_files = fileupload_service.finalize_uploads(question_create.image_files)

    # 2. 질문 생성
    db_question = Question(subject=question_create.subject,
                           content=question_create.content,
                           create_date=datetime.now(),
                           user=user)
    db.add(db_question)
    
    # 3. 이미지 파일 정보 저장
    for image_data in final_files:
        db_image = QuestionImage(
            filename=image_data['filename'],
            original_name=image_data['original_name'],
            thumbnail_filename=image_data.get('thumbnail_filename'),
            question=db_question
        )
        db.add(db_image)

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
    
    # 질문 삭제 시 모든 이미지 파일명에 'delete_' 접두어 추가
    for image in db_question.images:
        new_fn, new_tfn = fileupload_service.rename_to_deleted(image.filename, image.thumbnail_filename)
        image.filename = new_fn
        image.thumbnail_filename = new_tfn
        
    db.add(db_question)
    db.commit()

def update_question(db:Session, db_question:Question, question_update:QuestionUpdate):
    # 1. 새로 추가된 임시 파일이 있다면 최종 경로로 이동
    final_files = fileupload_service.finalize_uploads(question_update.image_files)
    
    # 2. 제목, 내용 수정
    db_question.subject = question_update.subject
    db_question.content = question_update.content
    db_question.modify_date = datetime.now()
    
    # 3. 수정 과정에서 제거된 이미지 파일 식별 및 격리
    existing_images = {img.filename: img for img in db_question.images}
    new_filenames = {img_data['filename'] for img_data in final_files}
    
    for filename, img_obj in existing_images.items():
        if filename not in new_filenames:
            # 새로운 리스트에 없는 기존 파일은 파일명 앞에 'delete_' 접두어 추가
            fileupload_service.rename_to_deleted(img_obj.filename, img_obj.thumbnail_filename)

    # 4. 기존 이미지 관계 초기화 및 새 리스트 등록
    db_question.images.clear()
    
    for image_data in final_files:
        db_image = QuestionImage(
            filename=image_data['filename'],
            original_name=image_data['original_name'],
            thumbnail_filename=image_data.get('thumbnail_filename'),
            question=db_question
        )
        db.add(db_image)

    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question