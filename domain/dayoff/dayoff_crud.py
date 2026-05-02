from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from models import DayOff
from domain.dayoff.dayoff_schema import DayOffCreate, DayOffStatus

def create_dayoff_list(db: Session, dayoff_create: DayOffCreate, user_id: int):
    if not dayoff_create.dates:
        return 0
        
    sorted_dates = sorted(dayoff_create.dates)
    start_str = sorted_dates[0].strftime('%Y%m%d')
    end_str = sorted_dates[-1].strftime('%Y%m%d')
    group_id = f"{start_str}-{end_str}"
    
    created_count = 0
    for date_item in sorted_dates:
        existing_dayoff = db.query(DayOff).filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.date == date_item,
                DayOff.is_deleted == False
            )
        ).first()
        
        if existing_dayoff:
            continue
            
        db_dayoff = DayOff(
            date=date_item,
            user_id=user_id,
            type=dayoff_create.type.value,
            status=DayOffStatus.REQUESTED.value,
            memo=dayoff_create.memo,
            group_id=group_id,
            create_date=datetime.now(),
            is_deleted=False
        )
        db.add(db_dayoff)
        created_count += 1
        
    db.commit()
    return created_count

def get_dayoff_list(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    """
    group_id별로 그룹화하여 목록을 조회합니다.
    """
    # 1. group_id별로 데이터를 묶어서 요약 정보 추출
    # group_id, type, status, memo, 시작일, 종료일, 전체 일수, 대표 ID
    query = db.query(
        DayOff.group_id,
        DayOff.type,
        DayOff.status,
        DayOff.memo,
        func.min(DayOff.date).label('start_date'),
        func.max(DayOff.date).label('end_date'),
        func.count(DayOff.id).label('total_days'),
        func.max(DayOff.create_date).label('create_date'),
        func.min(DayOff.id).label('representative_id') # 삭제 요청을 위해 사용할 ID
    ).filter(
        and_(DayOff.user_id == user_id, DayOff.is_deleted == False)
    ).group_by(
        DayOff.group_id, DayOff.type, DayOff.status, DayOff.memo
    ).order_by(
        func.min(DayOff.date).desc()
    )

    results = query.offset(skip).limit(limit).all()
    total_groups = db.query(func.count(func.distinct(DayOff.group_id))).filter(
        and_(DayOff.user_id == user_id, DayOff.is_deleted == False)
    ).scalar()

    # 스키마에 맞게 데이터 변환
    formatted_list = []
    for r in results:
        # 날짜 포맷팅 (예: 2026-03-06 ~ 2026-03-10)
        date_display = f"{r.start_date}"
        if r.start_date != r.end_date:
            date_display = f"{r.start_date} ~ {r.end_date} ({r.total_days}일)"
        
        formatted_list.append({
            "id": r.representative_id,
            "date": date_display, # 문자열로 전달 (프론트 표시용)
            "type": r.type,
            "status": r.status,
            "memo": r.memo,
            "group_id": r.group_id,
            "create_date": r.create_date,
            "user_id": user_id # 누락되었던 필드 추가
        })

    return formatted_list, total_groups

def delete_dayoff(db: Session, dayoff_id: int, user_id: int):
    db_dayoff = db.query(DayOff).filter(DayOff.id == dayoff_id).first()
    if not db_dayoff or db_dayoff.user_id != user_id:
        return False
        
    now = datetime.now()
    if db_dayoff.group_id:
        group_items = db.query(DayOff).filter(
            and_(DayOff.user_id == user_id, DayOff.group_id == db_dayoff.group_id)
        ).all()
        for item in group_items:
            item.is_deleted = True
            item.delete_date = now
    else:
        db_dayoff.is_deleted = True
        db_dayoff.delete_date = now
        
    db.commit()
    return True
