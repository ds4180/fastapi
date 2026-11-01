import logging
from sqlalchemy.orm import Session
from models import SystemTask
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger("task_service")

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


def calculate_next_scheduled_at(
    cron_expr: Optional[str] = None,
    interval_sec: Optional[int] = None,
    base_time: Optional[datetime] = None
) -> Optional[datetime]:
    """
    [차기 스케줄 일시 계산기]
    cron_expression 또는 repeat_interval을 기반으로 다음 실행 예정 일시를 계산합니다.
    croniter가 없을 경우를 대비한 안전 폴백을 내장합니다.
    """
    base = base_time or datetime.now()

    if cron_expr:
        if HAS_CRONITER:
            try:
                itr = croniter(cron_expr, base)
                return itr.get_next(datetime)
            except Exception as e:
                logger.error(f"Cron 표현식 파싱 실패 ({cron_expr}): {e}")
                return None
        else:
            # croniter 미설치 시 기본 패턴 폴백 파싱 (예: "*/5 * * * *", "0 0 * * *")
            parts = cron_expr.strip().split()
            if len(parts) == 5:
                minute_part = parts[0]
                if minute_part.startswith("*/"):
                    try:
                        step_min = int(minute_part.split("/")[1])
                        return base + timedelta(minutes=step_min)
                    except ValueError:
                        pass
            # 기본 1시간 후 폴백
            logger.warning(f"croniter 모듈이 없어 Cron({cron_expr})을 1시간 후로 기본 폴백 예약합니다.")
            return base + timedelta(hours=1)

    elif interval_sec and interval_sec > 0:
        return base + timedelta(seconds=interval_sec)

    return None


def enqueue_task(
    db: Session,
    task_type: str,
    payload: Dict[str, Any],
    priority: int = 5,
    scheduled_at: Optional[datetime] = None,
    cron_expression: Optional[str] = None,
    repeat_interval: Optional[int] = None,
    unique_key: Optional[str] = None,
    parent_id: Optional[int] = None,
    created_by: Optional[int] = None,
    tags: Optional[list] = None,
    max_retries: int = 3,
    timeout_sec: int = 300
) -> SystemTask:
    """
    [범용 태스크 등록 함수]
    어떤 비즈니스 로직에서도 이 함수를 호출하여 비동기 작업 및 반복 스케줄을 예약할 수 있습니다.
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
        cron_expression=cron_expression,
        repeat_interval=repeat_interval,
        unique_key=unique_key,
        parent_id=parent_id,
        created_by=created_by,
        tags=tags or [],
        max_retries=max_retries,
        timeout_sec=timeout_sec,
        status="PENDING"
    )
    
    db.add(new_task)
    db.flush() # ID를 즉시 생성하기 위해 호출 (커밋은 호출한 곳에서 수행)
    return new_task

