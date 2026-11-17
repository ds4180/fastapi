"""
============================================================================
[통합 일정 관리 라우터 (domain/v1/schedule/schedule_router.py)]
============================================================================
"""

import calendar
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from core.deps import get_current_user
from core.audit import safe_log_audit
from models import User

from . import schedule_schema as schema
from . import schedule_service as service

router = APIRouter(prefix="/v1/schedule", tags=["Schedule"])


def _resolve_date_window(
    year: Optional[int],
    month: Optional[int],
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[date, date]:
    if start_date and end_date:
        try:
            s_d = date.fromisoformat(start_date[:10])
            e_d = date.fromisoformat(end_date[:10])
            return (s_d, e_d if e_d >= s_d else s_d)
        except ValueError:
            raise HTTPException(status_code=400, detail="유효하지 않은 날짜 형식입니다.")

    today = date.today()
    y = year if year and 1970 <= year <= 2100 else today.year
    m = month if month and 1 <= month <= 12 else today.month
    first_day = date(y, m, 1)
    last_day = date(y, m, calendar.monthrange(y, m)[1])
    # 6주 달력 앞뒤 인접 주(최대 7일) 포함 조회
    return (first_day - timedelta(days=7), last_day + timedelta(days=7))


@router.get("")
def list_schedules(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    월간/기간별 통합 일정 조회:
    - 개인 일정 + 전사 공지/공휴일
    - 본인 결근계(개인 스케줄 포함)
    - Tier 2(Rank 2+): 사무실 일정 및 사무실 직원 전체 결근계 포함
    """
    s_d, e_d = _resolve_date_window(year, month, start_date, end_date)
    return service.get_schedules_for_user(db, current_user, s_d, e_d)


@router.post("")
def create_schedule(
    payload: schema.ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = service.create_schedule(db, current_user, payload)
    safe_log_audit(
        db=db,
        app_id="schedule",
        log_type="CHANGE",
        action="SCHEDULE_CREATED",
        title=f"[일정] {obj.title} ({obj.category})",
        user=current_user,
        resource_type="schedule",
        resource_id=str(obj.id),
    )
    return {"message": "일정이 등록되었습니다.", "id": obj.id}


@router.patch("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: schema.ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = service.update_schedule(db, current_user, schedule_id, payload)
    safe_log_audit(
        db=db,
        app_id="schedule",
        log_type="CHANGE",
        action="SCHEDULE_UPDATED",
        title=f"[일정 수정] {obj.title} ({obj.category})",
        user=current_user,
        resource_type="schedule",
        resource_id=str(obj.id),
    )
    return {"message": "일정이 수정되었습니다.", "id": obj.id}


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.delete_schedule(db, current_user, schedule_id)
    safe_log_audit(
        db=db,
        app_id="schedule",
        log_type="CHANGE",
        action="SCHEDULE_DELETED",
        title=f"[일정 삭제] #{schedule_id}",
        user=current_user,
        resource_type="schedule",
        resource_id=str(schedule_id),
    )
    return {"message": "일정이 삭제되었습니다.", "id": schedule_id}
