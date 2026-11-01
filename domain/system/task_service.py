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


def bootstrap_default_cron_tasks(db: Session) -> int:
    """
    [자율신경계 필수 Cron 태스크 자동 시드 (Startup Bootstrap)]
    시스템 최초 가동 또는 재시작 시, 자율신경계가 무인으로 순환하기 위한
    핵심 4대 정기 스케줄러 태스크를 DB에 자동 등록합니다.
    (이미 PENDING 또는 RUNNING 상태인 작업이 있으면 중복 등록하지 않음)
    """
    core_cron_definitions = [
        {
            "task_type": "DYNAMIC_GROUP_REFRESH",
            "unique_key": "cron:dynamic_group_refresh",
            "payload": {},
            "priority": 3,
            "repeat_interval": 600, # 10분마다
            "cron_expression": None,
            "tags": ["core", "dynamic_group", "cron"],
            "desc": "기사·휴무·배차 동적 그룹 10분 주기 실시간 자율 연산"
        },
        {
            "task_type": "SYSTEM_WATCHDOG_INSPECTION",
            "unique_key": "cron:system_watchdog_inspection",
            "payload": {},
            "priority": 2,
            "repeat_interval": 300, # 5분마다
            "cron_expression": None,
            "tags": ["core", "watchdog", "cron"],
            "desc": "시스템 이상 징후(워커 실패/보안 침해/지시 미확인) 5분 주기 감시"
        },
        {
            "task_type": "DATA_RETENTION_GC",
            "unique_key": "cron:data_retention_gc",
            "payload": {},
            "priority": 8,
            "repeat_interval": None,
            "cron_expression": "0 3 * * *", # 매일 새벽 03:00
            "tags": ["core", "retention", "gc", "cron"],
            "desc": "만료 데이터(감사로그/세션/태스크) 및 Redis 메모리 매일 새벽 03:00 정기 정리"
        },
        {
            "task_type": "MEDIA_GC",
            "unique_key": "cron:media_gc",
            "payload": {"indices": [1, 2, 3, 4, 5]},
            "priority": 8,
            "repeat_interval": None,
            "cron_expression": "0 4 * * *", # 매일 새벽 04:00
            "tags": ["core", "media", "gc", "cron"],
            "desc": "미디어 임시 파일 및 삭제 자산 매일 새벽 04:00 정기 가비지 컬렉션"
        }
    ]

    registered_count = 0
    now = datetime.now()

    for defn in core_cron_definitions:
        existing = db.query(SystemTask).filter(
            SystemTask.unique_key == defn["unique_key"]
        ).first()

        if not existing:
            next_time = calculate_next_scheduled_at(
                cron_expr=defn["cron_expression"],
                interval_sec=defn["repeat_interval"],
                base_time=now
            ) or now

            enqueue_task(
                db=db,
                task_type=defn["task_type"],
                payload=defn["payload"],
                priority=defn["priority"],
                scheduled_at=next_time,
                cron_expression=defn["cron_expression"],
                repeat_interval=defn["repeat_interval"],
                unique_key=defn["unique_key"],
                tags=defn["tags"]
            )
            registered_count += 1
            logger.info(f"🌱 [Bootstrap] 자율신경계 정기 태스크 등록 완료: {defn['task_type']} ({defn['desc']})")

    if registered_count > 0:
        db.commit()

    return registered_count

