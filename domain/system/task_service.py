import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import SystemTask

logger = logging.getLogger("task_service")

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


def calculate_next_scheduled_at(
    cron_expr: Optional[str] = None,
    interval_sec: Optional[int] = None,
    base_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    [차기 스케줄 일시 계산기]
    cron_expression 또는 repeat_interval을 기반으로 다음 실행 예정 일시를 계산합니다.
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
            parts = cron_expr.strip().split()
            if len(parts) == 5:
                m_str, h_str, dom_str, mon_str, dow_str = parts

                if m_str.isdigit() and h_str.isdigit() and dom_str == "*" and mon_str == "*" and dow_str == "*":
                    target_hour = int(h_str)
                    target_min = int(m_str)
                    candidate = base.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
                    if candidate <= base:
                        candidate += timedelta(days=1)
                    return candidate

                if m_str.startswith("*/"):
                    try:
                        step_min = int(m_str.split("/")[1])
                        return base + timedelta(minutes=step_min)
                    except ValueError:
                        pass

                if m_str.isdigit() and h_str == "*":
                    target_min = int(m_str)
                    candidate = base.replace(minute=target_min, second=0, microsecond=0) + timedelta(hours=1)
                    return candidate

            logger.warning(f"Cron({cron_expr}) 패턴을 1시간 후로 기본 폴백 예약합니다.")
            return base + timedelta(hours=1)

    elif interval_sec and interval_sec > 0:
        return base + timedelta(seconds=interval_sec)

    return None


def enqueue_task(
    db: Session,
    task_type: str,
    payload: Dict[str, Any],
    priority: Optional[int] = None,
    scheduled_at: Optional[datetime] = None,
    cron_expression: Optional[str] = None,
    repeat_interval: Optional[int] = None,
    unique_key: Optional[str] = None,
    parent_id: Optional[int] = None,
    created_by: Optional[int] = None,
    tags: Optional[list] = None,
    max_retries: Optional[int] = None,
    timeout_sec: Optional[int] = None,
) -> SystemTask:
    """
    [범용 태스크 등록 함수]
    미지정 옵션(priority, max_retries, timeout_sec)은 동적 정책(task_settings) 기본값을 자동 주입합니다.
    """
    from domain.system.task_policy_service import get_cached_task_settings

    cfg = get_cached_task_settings(db)
    eff_priority = int(priority if priority is not None else cfg.get("default_priority", 5))
    eff_retries = int(max_retries if max_retries is not None else cfg.get("default_max_retries", 3))
    eff_timeout = int(timeout_sec if timeout_sec is not None else cfg.get("default_timeout_sec", 300))

    if unique_key:
        existing = db.query(SystemTask).filter(SystemTask.unique_key == unique_key).first()
        if existing:
            if existing.status in ["PENDING", "RUNNING", "SUCCESS"]:
                return existing

            existing.status = "PENDING"
            existing.payload = payload
            existing.priority = eff_priority
            existing.scheduled_at = scheduled_at or datetime.now()
            existing.retry_count = 0
            existing.error_log = None
            existing.progress_pct = 0
            existing.started_at = None
            existing.completed_at = None
            db.flush()
            return existing

    new_task = SystemTask(
        task_type=task_type,
        payload=payload,
        priority=eff_priority,
        scheduled_at=scheduled_at or datetime.now(),
        cron_expression=cron_expression,
        repeat_interval=repeat_interval,
        unique_key=unique_key,
        parent_id=parent_id,
        created_by=created_by,
        tags=tags or [],
        max_retries=eff_retries,
        timeout_sec=eff_timeout,
        status="PENDING",
    )

    db.add(new_task)
    db.flush()
    return new_task


def bootstrap_default_cron_tasks(db: Session) -> int:
    """
    [자율신경계 필수 정기 태스크 자동 시드 (동적 정책 기반)]
    하드코딩 사양 대신 SystemConfig('task_settings')의 core_schedules 및
    bootstrap_heal_stuck_sec 설정을 기준으로 정기 태스크를 시드·자가치유합니다.
    """
    from domain.system.task_policy_service import get_task_settings

    settings = get_task_settings(db)
    heal_stuck_sec = int(settings.get("bootstrap_heal_stuck_sec", 600))
    core_schedules = settings.get("core_schedules", [])

    registered_count = 0
    now = datetime.now()

    from sqlalchemy import or_

    for defn in core_schedules:
        ukey_prefix = defn["unique_key"]
        existing = (
            db.query(SystemTask)
            .filter(
                SystemTask.task_type == defn["task_type"],
                or_(SystemTask.cron_expression.is_not(None), SystemTask.repeat_interval.is_not(None)),
                or_(SystemTask.unique_key.like(f"{ukey_prefix}%"), SystemTask.unique_key.is_(None)),
                SystemTask.status.in_(["PENDING", "RUNNING", "FAILED", "CANCELLED"]),
            )
            .order_by(SystemTask.id.desc())
            .first()
        )

        # 설정 탭에서 비활성화(enabled=False)된 핵심 스케줄은 부트스트랩 시 강제 생성하지 않음
        if not defn.get("enabled", True):
            if existing and existing.status == "PENDING":
                existing.status = "CANCELLED"
                registered_count += 1
            continue

        if not existing:
            next_time = (
                calculate_next_scheduled_at(
                    cron_expr=defn["cron_expression"],
                    interval_sec=defn["repeat_interval"],
                    base_time=now,
                )
                or now
            )
            enqueue_task(
                db=db,
                task_type=defn["task_type"],
                payload=defn["payload"],
                priority=defn["priority"],
                scheduled_at=next_time,
                cron_expression=defn["cron_expression"],
                repeat_interval=defn["repeat_interval"],
                unique_key=defn["unique_key"],
                tags=defn["tags"],
            )
            registered_count += 1
            logger.info(f"🌱 [Bootstrap] 자율신경계 정기 태스크 등록 완료: {defn['task_type']}")
        else:
            needs_heal = False
            if existing.status in ("FAILED", "CANCELLED"):
                existing.status = "PENDING"
                existing.retry_count = 0
                existing.error_log = None
                existing.worker_id = None
                needs_heal = True
            elif existing.status == "RUNNING":
                started = existing.started_at or existing.scheduled_at or now
                if (now - started).total_seconds() > heal_stuck_sec:
                    logger.warning(
                        f"⚠️ [Bootstrap Auto-Heal] 장기 RUNNING 고착 태스크 복구: {existing.id} ({existing.task_type})"
                    )
                    existing.status = "PENDING"
                    existing.worker_id = None
                    needs_heal = True

            if existing.cron_expression != defn["cron_expression"]:
                existing.cron_expression = defn["cron_expression"]
                needs_heal = True
            if existing.repeat_interval != defn["repeat_interval"]:
                existing.repeat_interval = defn["repeat_interval"]
                needs_heal = True
            if existing.priority != defn["priority"]:
                existing.priority = defn["priority"]
                needs_heal = True
            if existing.payload != defn["payload"]:
                existing.payload = defn["payload"]
                flag_modified(existing, "payload")
                needs_heal = True

            if needs_heal:
                existing.scheduled_at = (
                    calculate_next_scheduled_at(
                        cron_expr=defn["cron_expression"],
                        interval_sec=defn["repeat_interval"],
                        base_time=now,
                    )
                    or now
                )
                registered_count += 1
                logger.info(
                    f"✨ [Bootstrap] 핵심 정기 태스크 자가치유/사양 동기화 완료: {defn['task_type']}"
                )

    if registered_count > 0:
        db.commit()

    return registered_count
