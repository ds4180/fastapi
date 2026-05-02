from sqlalchemy.orm import Session
from models import SystemTask
from datetime import datetime
from typing import Any, Dict, Optional

def enqueue_task(
    db: Session,
    task_type: str,
    payload: Dict[str, Any],
    priority: int = 5,
    scheduled_at: Optional[datetime] = None,
    unique_key: Optional[str] = None,
    created_by: Optional[int] = None,
    tags: Optional[list] = None
) -> SystemTask:
    """
    [범용 태스크 등록 함수]
    어떤 비즈니스 로직에서도 이 함수를 호출하여 비동기 작업을 예약할 수 있습니다.
    이 함수는 DB 레코드만 생성하며, 실제 실행은 task_worker가 담당합니다.
    """
    
    # 멱등성 체크: 만약 unique_key가 있고, 이미 PENDING인 동일 작업이 있다면 새로 만들지 않음
    if unique_key:
        existing = db.query(SystemTask).filter(
            SystemTask.unique_key == unique_key,
            SystemTask.status == "PENDING"
        ).first()
        if existing:
            return existing

    new_task = SystemTask(
        task_type=task_type,
        payload=payload,
        priority=priority,
        scheduled_at=scheduled_at or datetime.now(),
        unique_key=unique_key,
        created_by=created_by,
        tags=tags or [],
        status="PENDING"
    )
    
    db.add(new_task)
    db.flush() # ID를 즉시 생성하기 위해 호출 (커밋은 호출한 곳에서 수행)
    return new_task
