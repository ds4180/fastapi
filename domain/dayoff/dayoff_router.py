from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette import status

from database import get_db
from domain.dayoff import dayoff_schema, dayoff_crud
from domain.user.user_router import get_current_user
from models import User

router = APIRouter(
    prefix="/dayoff",
)

@router.get("/quota-status")
def dayoff_quota_status(
    year: Optional[int] = Query(None, description="조회 연도 (기본: 올해)"),
    month: Optional[int] = Query(None, description="조회 월 1~12 (기본: 이번 달)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    현재 로그인한 사용자의 결근 운영 방식(APPROVAL vs FCFS) 및 지정 연/월의 일자별 선착순 정원 현황을 반환합니다.
    """
    now = datetime.now()
    y = year if year and 1970 <= year <= 2100 else now.year
    m = month if month and 1 <= month <= 12 else now.month
    return dayoff_crud.get_monthly_quota_status(db, y, m, current_user)

@router.post("/create", status_code=status.HTTP_204_NO_CONTENT)
def dayoff_create(
    _dayoff_create: dayoff_schema.DayOffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    휴무일 등록 (다중 날짜 - 사무직 승인대기 / 운전직 선착순 정원 검사 후 즉시 확정)
    """
    dayoff_crud.create_dayoff_list(db, _dayoff_create, current_user.id)

@router.get("/list", response_model=dayoff_schema.DayOffListResponse)
def dayoff_list(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    휴무일 목록 조회
    """
    _list, total = dayoff_crud.get_dayoff_list(db, current_user.id, skip, limit)
    return {"total": total, "data": _list}

@router.delete("/delete/{dayoff_id}", status_code=status.HTTP_204_NO_CONTENT)
def dayoff_delete(
    dayoff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    휴무일 삭제
    """
    result = dayoff_crud.delete_dayoff(db, dayoff_id, current_user.id)
    
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="데이터를 찾을 수 없습니다.")
    elif result is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="이미 경과한 승인 휴무이거나 삭제 권한이 없습니다.")

