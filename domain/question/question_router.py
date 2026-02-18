from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from starlette import status



from database import get_db
from domain.question import question_schema, question_crud
from domain.user.user_router import get_current_user, get_current_user_optional
from models import User




router = APIRouter(
    prefix="/api/question",
)

@router.get("/list", response_model=question_schema.QuestionList)
def question_list(db: Session = Depends(get_db),
                  page: int = 0, size: int = 10,
                  current_user: User = Depends(get_current_user_optional)):
    total, _question_list = question_crud.get_question_list(
        db, skip=page*size, limit=size, user=current_user)
    return {
        'total': total,
        'question_list': _question_list
    }
# @router.get("/list", response_model=list[question_schema.Question])
# async def question_list(db:Session = Depends(get_db)):
#     _question_list = question_crud.get_question_list(db)
#     return _question_list -- 페이징으로 작동하면서 업그레이드 시킴


@router.get("/detail/{question_id}", response_model=question_schema.Question)
def question_detail(question_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    _question = question_crud.get_question(db, question_id, user=current_user)
    if not _question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="질문을 찾을 수 없습니다.")
    return _question

@router.post("/read/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def question_read(question_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    db_question = question_crud.get_question(db, question_id)
    if not db_question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="질문을 찾을 수 없습니다.")
    question_crud.add_read_user(db, db_question, current_user)

@router.delete("/read/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def question_unread(question_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    db_question = question_crud.get_question(db, question_id)
    if not db_question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="질문을 찾을 수 없습니다.")
    question_crud.remove_read_user(db, db_question, current_user)

@router.post("/reaction", status_code=status.HTTP_204_NO_CONTENT)
def question_reaction(_reaction_create: question_schema.QuestionReactionCreate,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    db_question = question_crud.get_question(db, _reaction_create.question_id)
    if not db_question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="질문을 찾을 수 없습니다.")
    question_crud.toggle_reaction(db, db_question, current_user, _reaction_create.reaction_type)

@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=question_schema.Question)
def question_create(_question_create: question_schema.QuestionCreate,
                          db:Session = Depends(get_db),
                          current_user:User = Depends(get_current_user)):
    return question_crud.create_question(db, question_create=_question_create, user=current_user)


@router.put("/update", status_code=status.HTTP_204_NO_CONTENT)
def question_update(_question_update:question_schema.QuestionUpdate,
                    db:Session = Depends(get_db),
                    current_user:User = Depends(get_current_user)):
    db_question = question_crud.get_question(db, question_id=_question_update.question_id)
    if not db_question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="데이터를 찾을 수 없습니다.")
    if current_user.id != db_question.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="수정 권한이 없습니다.")
    question_crud.update_question(db, db_question=db_question, question_update=_question_update)


@router.delete("/delete", status_code=status.HTTP_204_NO_CONTENT)
def question_delete(_question_delete: question_schema.QuestionDelete,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    db_question = question_crud.get_question(db, question_id=_question_delete.question_id)
    if not db_question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="데이터를 찾을 수 없습니다.")
    if current_user.id != db_question.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="삭제 권한이 없습니다.")
    question_crud.delete_question(db, db_question=db_question)