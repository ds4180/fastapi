from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models import DayOff
from domain.dayoff.dayoff_schema import DayOffCreate, DayOffStatus

def create_dayoff_list(db: Session, dayoff_create: DayOffCreate, user_id: int):
    """
    여러 날짜의 휴무일을 한 번에 등록합니다.
    이미 등록된 날짜가 있다면 건너뛰거나 에러를 발생시킬 수 있습니다.
    여기서는 '중복되지 않은 날짜만' 등록하는 방식으로 구현합니다.
    """
    created_count = 0
    
    for date_item in dayoff_create.dates:
        # 중복 체크: 해당 사용자가 해당 날짜에 이미 등록한 내역이 있는지 확인
        existing_dayoff = db.query(DayOff).filter(
            and_(
                DayOff.user_id == user_id,
                DayOff.date == date_item
            )
        ).first()
        
        if existing_dayoff:
            continue # 이미 있으면 스킵
            
        # 새 휴무일 객체 생성
        db_dayoff = DayOff(
            date=date_item,
            user_id=user_id,
            type=dayoff_create.type.value,
            status=DayOffStatus.REQUESTED.value, # 기본값: 신청
            memo=dayoff_create.memo,
            create_date=datetime.now()
        )
        db.add(db_dayoff)
        created_count += 1
        
    db.commit()
    return created_count

def get_dayoff_list(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    """
    특정 사용자의 휴무일 목록을 조회합니다.
    날짜 내림차순(최근 날짜가 위로)으로 정렬합니다.
    """
    _list = db.query(DayOff).filter(DayOff.user_id == user_id)\
            .order_by(DayOff.date.desc())\
            .offset(skip).limit(limit).all()
    total = db.query(DayOff).filter(DayOff.user_id == user_id).count()
    return _list, total

def delete_dayoff(db: Session, dayoff_id: int, user_id: int):
    """
    휴무일 삭제 (본인 데이터만 삭제 가능)
    """
    db_dayoff = db.query(DayOff).filter(DayOff.id == dayoff_id).first()
    
    if not db_dayoff:
        return None # 존재하지 않음
        
    if db_dayoff.user_id != user_id:
        # 권한 없음 (본인 글 아님). 예외 처리는 Router에서 하거나 여기서 raise 가능.
        # 일단 None 반환하여 Router에서 처리하도록 유도
        return False
        
    db.delete(db_dayoff)
    db.commit()
    return True
