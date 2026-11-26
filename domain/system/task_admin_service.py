"""
============================================================================
[관리자 태스크 관제·CRUD 비즈니스 서비스 (domain/system/task_admin_service.py)]
============================================================================
- task_admin_router.py에 직접 작성되어 있던 집계 쿼리, 필터링 검색, 생성/수정/재시도,
  단일 취소·삭제 및 상태별 일괄 정리 로직을 서비스 계층으로 분리합니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from domain.system.task_policy_service import DEFAULT_TASK_METADATA, get_task_settings
from domain.system.task_service import calculate_next_scheduled_at
from domain.v1.admin.admin_schema import SystemTaskCreate, SystemTaskUpdate
from models import SystemTask


def get_tasks_summary_data(db: Session) -> Dict[str, Any]:
    """상단 4대 워커 관제 지표 집계 (실제 worker_enabled 정책 반영)"""
    settings = get_task_settings(db)
    pending_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "PENDING").scalar() or 0
    running_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "RUNNING").scalar() or 0
    failed_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "FAILED").scalar() or 0
    scheduler_count = (
        db.query(func.count(SystemTask.id))
        .filter(
            SystemTask.status.in_(["PENDING", "RUNNING"]),
            or_(SystemTask.cron_expression.is_not(None), SystemTask.repeat_interval.is_not(None)),
        )
        .scalar()
        or 0
    )
    since_24h = datetime.now() - timedelta(hours=24)
    completed_24h = (
        db.query(func.count(SystemTask.id))
        .filter(SystemTask.status == "SUCCESS", SystemTask.completed_at >= since_24h)
        .scalar()
        or 0
    )

    worker_enabled = bool(settings.get("worker_enabled", True))
    return {
        "worker_status": "ONLINE" if worker_enabled else "PAUSED",
        "worker_enabled": worker_enabled,
        "poll_interval_sec": settings.get("worker_poll_interval_sec", 2),
        "pending_count": pending_count,
        "running_count": running_count,
        "failed_count": failed_count,
        "scheduler_count": scheduler_count,
        "completed_24h_count": completed_24h,
    }


def get_registered_task_types() -> List[Dict[str, Any]]:
    """현재 등록된 모든 워커 핸들러 목록과 한글 메타데이터 가이드를 반환합니다."""
    from domain.system.task_worker import TASK_HANDLERS

    result: List[Dict[str, Any]] = []
    for task_type in TASK_HANDLERS.keys():
        meta = DEFAULT_TASK_METADATA.get(
            task_type,
            {
                "label": task_type,
                "description": f"시스템 백그라운드 비동기 작업 ({task_type})",
                "category": "기타",
                "icon": "solar:cpu-bolt-bold-duotone",
                "example": {},
            },
        )
        result.append(
            {
                "type": task_type,
                "label": meta["label"],
                "description": meta["description"],
                "category": meta["category"],
                "icon": meta["icon"],
                "example": meta.get("example", {}),
            }
        )
    return result


def query_tasks_list(
    db: Session,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    is_scheduler: Optional[bool] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """상태·타입·정기여부·검색어로 필터링된 태스크 목록 조회"""
    settings = get_task_settings(db)
    effective_limit = min(max(int(limit or settings.get("ui_page_limit", 50)), 1), 200)

    query = db.query(SystemTask)
    if status:
        query = query.filter(SystemTask.status == status)
    if task_type:
        query = query.filter(SystemTask.task_type == task_type)

    if is_scheduler is True:
        query = query.filter(
            or_(SystemTask.cron_expression.is_not(None), SystemTask.repeat_interval.is_not(None))
        )
        if not status:
            query = query.filter(SystemTask.status.in_(["PENDING", "RUNNING"]))
    elif is_scheduler is False:
        query = query.filter(
            SystemTask.cron_expression.is_(None),
            SystemTask.repeat_interval.is_(None),
        )

    if search and search.strip():
        q = search.strip()
        conds = [
            SystemTask.task_type.ilike(f"%{q}%"),
            SystemTask.unique_key.ilike(f"%{q}%"),
        ]
        if q.lstrip("#").isdigit():
            conds.append(SystemTask.id == int(q.lstrip("#")))
        query = query.filter(or_(*conds))

    total = query.count()
    order_col = (
        SystemTask.scheduled_at.asc()
        if (is_scheduler is True and not status)
        else desc(SystemTask.created_at)
    )
    tasks = query.order_by(order_col).offset(max(0, offset)).limit(effective_limit).all()
    return {"total": total, "tasks": tasks}


def create_manual_task(db: Session, task_in: SystemTaskCreate, admin_id: int) -> SystemTask:
    """관리자 수동 태스크 생성 (미지정 시 동적 정책 기본값 적용 및 차기 스케줄 계산)"""
    data = task_in.model_dump()
    now = datetime.now()

    if not data.get("scheduled_at"):
        if data.get("cron_expression") or data.get("repeat_interval"):
            data["scheduled_at"] = (
                calculate_next_scheduled_at(
                    cron_expr=data.get("cron_expression"),
                    interval_sec=data.get("repeat_interval"),
                    base_time=now,
                )
                or now
            )
        else:
            data["scheduled_at"] = now

    if data.get("unique_key"):
        existing = db.query(SystemTask).filter(SystemTask.unique_key == data["unique_key"]).first()
        if existing:
            if existing.status in ("PENDING", "RUNNING"):
                raise HTTPException(
                    status_code=409,
                    detail=f"동일한 고유키('{data['unique_key']}')로 대기/실행 중인 작업(#{existing.id})이 이미 존재합니다.",
                )
            data["unique_key"] = f"{data['unique_key']}:{now.strftime('%Y%m%d%H%M%S')}"

    new_task = SystemTask(**data, status="PENDING", created_by=admin_id)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


def get_task_by_id(db: Session, task_id: int) -> SystemTask:
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    return task


def retry_task_by_id(db: Session, task_id: int, admin_username: str) -> SystemTask:
    task = get_task_by_id(db, task_id)
    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="현재 실행 중인 태스크는 재시도할 수 없습니다.")

    task.status = "PENDING"
    task.retry_count = 0
    task.worker_id = None
    task.error_log = f"[관리자 {admin_username}에 의해 재시도됨] {task.error_log or ''}".strip()
    task.scheduled_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def update_task_by_id(db: Session, task_id: int, task_in: SystemTaskUpdate) -> Tuple[SystemTask, List[str]]:
    task = get_task_by_id(db, task_id)
    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="현재 실행 중(RUNNING)인 작업은 수정할 수 없습니다.")

    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    if ("cron_expression" in update_data or "repeat_interval" in update_data) and "scheduled_at" not in update_data:
        re_next = calculate_next_scheduled_at(
            cron_expr=task.cron_expression,
            interval_sec=task.repeat_interval,
        )
        if re_next:
            task.scheduled_at = re_next

    db.commit()
    db.refresh(task)
    return task, list(update_data.keys())


def clear_tasks_by_status(db: Session, target_status: str = "FAILED") -> int:
    allowed = {"FAILED", "CANCELLED", "SUCCESS"}
    clean_status = (target_status or "FAILED").upper()
    if clean_status not in allowed:
        raise HTTPException(status_code=400, detail="일괄 정리는 FAILED, CANCELLED, SUCCESS 상태만 허용됩니다.")

    rows = db.query(SystemTask).filter(SystemTask.status == clean_status).all()
    count = len(rows)
    if count == 0:
        return 0
    for row in rows:
        db.delete(row)
    db.commit()
    return count


def cancel_or_delete_task_by_id(db: Session, task_id: int, hard_delete: bool = False) -> Tuple[str, str, bool]:
    """반환값: (task_type, 결과메시지, 영구삭제여부)"""
    task = get_task_by_id(db, task_id)
    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="이미 실행 중인 태스크는 삭제/취소할 수 없습니다.")

    task_type = task.task_type
    is_hard = hard_delete or task.status in ("FAILED", "CANCELLED")
    msg = f"태스크 #{task.id} 영구 삭제" if is_hard else f"태스크 #{task.id} 취소"

    if is_hard:
        db.delete(task)
    else:
        task.status = "CANCELLED"
    db.commit()
    return task_type, msg, is_hard
