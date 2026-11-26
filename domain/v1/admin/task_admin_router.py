"""
============================================================================
[관리자 비동기 태스크·스케줄러 라우터 (domain/v1/admin/task_admin_router.py)]
============================================================================
- 모든 집계·쿼리·정책 동기화 비즈니스 로직은 task_admin_service 및 task_policy_service로 분리하고,
  본 라우터는 HTTP 입출력, AppRegistry('tasks') 4단계 권한 인가 및 감사로그 기록만 담당합니다.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import require_app_permission
from core.permission import ROOT_RANK, can_access_app, get_user_rank
from database import get_db
from domain.system.task_admin_service import (
    cancel_or_delete_task_by_id,
    clear_tasks_by_status,
    create_manual_task,
    get_registered_task_types,
    get_task_by_id,
    get_tasks_summary_data,
    query_tasks_list,
    retry_task_by_id,
    update_task_by_id,
)
from domain.system.task_policy_service import (
    DEFAULT_TASK_METADATA as TASK_METADATA,
    get_task_settings,
    update_task_settings,
)
from models import AppRegistry, User

from .admin_schema import SystemTaskCreate, SystemTaskUpdate

router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin_tasks"],
)

check_task_read = require_app_permission("tasks", action="read")
check_task_write = require_app_permission("tasks", action="write")


def _can_write_tasks(user: User, db: Session) -> bool:
    if get_user_rank(user) == ROOT_RANK:
        return True
    app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "tasks").first()
    if not app_meta:
        return get_user_rank(user) >= 8
    return can_access_app(user, app_meta, action="write")


@router.get("/settings")
def get_task_settings_api(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read),
):
    """비동기 태스크 워커·스케줄러 통합 정책 설정 조회"""
    return {
        "settings": get_task_settings(db),
        "permissions": {
            "can_write": _can_write_tasks(admin, db),
        },
    }


@router.put("/settings")
def update_task_settings_api(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    """비동기 태스크 워커·스케줄러 정책 설정 저장 및 6대 정기 스케줄 DB 즉시 동기화"""
    old_cfg, new_cfg = update_task_settings(db, payload)
    diff_payload = [
        {"field": k, "from": old_cfg.get(k), "to": new_cfg.get(k)}
        for k in new_cfg
        if old_cfg.get(k) != new_cfg.get(k)
    ]
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="CHANGE",
        severity="INFO",
        action="TASK_SETTINGS_UPDATED",
        title=f"관리자({admin.username})에 의한 태스크·워커 정책 설정 변경",
        user=admin,
        resource_type="system_config",
        resource_id="task_settings",
        diff_payload=diff_payload,
        message=f"태스크·워커 정책 설정 {len(diff_payload)}개 항목을 갱신했습니다.",
    )
    return {"message": "태스크·워커 정책 설정이 저장되었습니다.", "settings": new_cfg}


@router.get("/summary")
def get_tasks_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read),
):
    return get_tasks_summary_data(db)


@router.get("/types")
def list_task_types(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read),
):
    return get_registered_task_types()


@router.get("")
def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    is_scheduler: Optional[bool] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read),
):
    return query_tasks_list(
        db=db,
        status=status,
        task_type=task_type,
        is_scheduler=is_scheduler,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post("")
def create_task(
    task_in: SystemTaskCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    new_task = create_manual_task(db, task_in, admin_id=admin.id)
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="CHANGE",
        severity="INFO",
        action="TASK_CREATED",
        title=f"관리자({admin.username})에 의한 태스크 #{new_task.id} ({new_task.task_type}) 등록",
        user=admin,
        resource_type="system_task",
        resource_id=str(new_task.id),
        message=f"작업 유형: {new_task.task_type}, 크론: {new_task.cron_expression or '단발성'}, 우선순위: {new_task.priority}",
        metadata={"task_id": new_task.id, "task_type": new_task.task_type},
    )
    return new_task


@router.delete("/failed/clear")
def clear_all_failed_tasks(
    target_status: str = "FAILED",
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    count = clear_tasks_by_status(db, target_status=target_status)
    if count == 0:
        return {"message": f"삭제할 {target_status} 상태 태스크가 없습니다.", "deleted_count": 0}

    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="SECURITY",
        severity="INFO",
        action="FAILED_TASKS_CLEARED",
        title=f"관리자({admin.username})에 의한 {target_status} 태스크 {count}건 일괄 영구 삭제",
        user=admin,
        resource_type="system_task",
        resource_id=f"ALL_{target_status}",
        message=f"{target_status} 상태 태스크 {count}건 영구 정리 완료",
        metadata={"deleted_count": count, "target_status": target_status},
    )
    return {"message": f"{target_status} 상태 태스크 {count}건이 일괄 삭제되었습니다.", "deleted_count": count}


@router.get("/{task_id}")
def get_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read),
):
    return get_task_by_id(db, task_id)


@router.post("/{task_id}/retry")
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    task = retry_task_by_id(db, task_id, admin_username=admin.username)
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="SECURITY",
        severity="WARN",
        action="TASK_RETRIED",
        title=f"관리자({admin.username})에 의한 태스크 #{task.id} 강제 재실행",
        user=admin,
        resource_type="system_task",
        resource_id=str(task.id),
        message=f"작업 #{task.id} ({task.task_type})을 PENDING 상태로 재투입했습니다.",
        metadata={"task_id": task.id, "task_type": task.task_type},
    )
    return {"message": "태스크가 다시 큐에 등록되었습니다.", "task_id": task.id}


@router.put("/{task_id}")
def update_task(
    task_id: int,
    task_in: SystemTaskUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    task, updated_fields = update_task_by_id(db, task_id, task_in)
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="CHANGE",
        severity="INFO",
        action="TASK_UPDATED",
        title=f"관리자({admin.username})에 의한 태스크 #{task.id} 스케줄/설정 수정",
        user=admin,
        resource_type="system_task",
        resource_id=str(task.id),
        message=f"작업 #{task.id} ({task.task_type}) 수정 완료 (스케줄: {task.scheduled_at}, 크론: {task.cron_expression})",
        metadata={"task_id": task.id, "task_type": task.task_type, "updated_fields": updated_fields},
    )
    return task


@router.delete("/{task_id}")
def cancel_or_delete_task(
    task_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write),
):
    task_type, msg, is_hard = cancel_or_delete_task_by_id(db, task_id, hard_delete=hard_delete)
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="SECURITY",
        severity="WARN",
        action="TASK_DELETED" if is_hard else "TASK_CANCELLED",
        title=f"관리자({admin.username})에 의한 {msg}",
        user=admin,
        resource_type="system_task",
        resource_id=str(task_id),
        message=f"작업 #{task_id} ({task_type}) {msg} 완료",
        metadata={"task_id": task_id, "task_type": task_type, "hard_delete": is_hard},
    )
    return {"message": f"{msg} 완료되었습니다.", "task_id": task_id, "hard_deleted": is_hard}
