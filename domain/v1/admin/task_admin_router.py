from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from database import get_db
from models import SystemTask, User
from core.deps import require_app_permission
from core.audit import safe_log_audit
from datetime import datetime
from typing import List, Optional, Dict, Any
from .admin_schema import SystemTaskCreate, SystemTaskUpdate

router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin_tasks"]
)

# 🏛️ AppRegistry 4단계 거버넌스 연동 (읽기: min_read_rank=8, 쓰기: min_write_rank=8)
check_task_read = require_app_permission("tasks", action="read")
check_task_write = require_app_permission("tasks", action="write")

# 📋 관리자가 한눈에 이해하는 쉬운 한글 메타데이터 매핑
TASK_METADATA: Dict[str, Dict[str, Any]] = {
    "MEDIA_GC": {
        "label": "스토리지 찌꺼기 청소",
        "description": "불필요한 임시 업로드 파일과 휴지통 잔여 데이터를 자동 정리하여 서버 디스크 공간을 확보합니다.",
        "category": "정리/보관",
        "icon": "solar:broom-bold-duotone",
        "example": {"indices": [1, 2, 3]}
    },
    "DYNAMIC_GROUP_REFRESH": {
        "label": "오늘 운행 기사 그룹 동기화",
        "description": "오늘 배차 및 휴무 일정과 대조하여 알림을 수신할 승무원 그룹(단체방)을 최신화합니다.",
        "category": "배차/동기화",
        "icon": "solar:users-group-two-rounded-bold-duotone",
        "example": {}
    },
    "THUMB_GEN": {
        "label": "사진 썸네일 축소판 생성",
        "description": "업로드된 원본 이미지를 모바일 기기에서 초고속으로 열 수 있도록 최적화된 작은 축소판을 만듭니다.",
        "category": "미디어",
        "icon": "solar:gallery-wide-bold-duotone",
        "example": {"asset_id": 1}
    },
    "MEDIA_BACKUP": {
        "label": "중요 사진·파일 안전 백업",
        "description": "지정된 첨부파일 자산들을 안전하게 압축하여 장기 보존용 저장소로 복제 백업합니다.",
        "category": "정리/보관",
        "icon": "solar:box-archive-bold-duotone",
        "example": {"asset_ids": [1, 2], "target_user_id": 1}
    },
    "MEDIA_ISOLATE": {
        "label": "의심 파일 격리 검역",
        "description": "보안 위험이 의심되는 파일을 일반 사용자가 접근할 수 없는 격리 검역소로 이동시킵니다.",
        "category": "보안",
        "icon": "solar:shield-warning-bold-duotone",
        "example": {"file_path": "/path/to/file", "asset_id": 1}
    }
}


@router.get("/summary")
def get_tasks_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read)
):
    """[관리자용] 상단 4대 로봇 일꾼(워커) 관제 요약 지표 집계"""
    pending_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "PENDING").scalar() or 0
    running_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "RUNNING").scalar() or 0
    failed_count = db.query(func.count(SystemTask.id)).filter(SystemTask.status == "FAILED").scalar() or 0
    scheduler_count = db.query(func.count(SystemTask.id)).filter(
        or_(SystemTask.cron_expression.is_not(None), SystemTask.repeat_interval.is_not(None))
    ).scalar() or 0

    return {
        "worker_status": "ONLINE",
        "pending_count": pending_count,
        "running_count": running_count,
        "failed_count": failed_count,
        "scheduler_count": scheduler_count
    }


@router.get("/types")
def list_task_types(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read)
):
    """[관리자용] 현재 시스템에 등록된 모든 태스크 유형과 가이드를 친절한 한글 메타데이터와 함께 조회합니다."""
    from domain.system.task_worker import TASK_HANDLERS
    
    result = []
    for t in TASK_HANDLERS.keys():
        meta = TASK_METADATA.get(t, {
            "label": t,
            "description": f"시스템 백그라운드 비동기 작업 ({t})",
            "category": "기타",
            "icon": "solar:cpu-bolt-bold-duotone",
            "example": {}
        })
        result.append({
            "type": t,
            "label": meta["label"],
            "description": meta["description"],
            "category": meta["category"],
            "icon": meta["icon"],
            "example": meta.get("example", {})
        })
    return result

@router.get("")
def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    is_scheduler: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read)
):
    """
    [관리자용] 모든 비동기 태스크 목록을 조회합니다.
    최신순으로 정렬하며 상태나 타입으로 필터링이 가능합니다.
    is_scheduler=True 이면 반복 작업(Cron/Interval)만 조회합니다.
    """
    query = db.query(SystemTask)
    
    if status:
        query = query.filter(SystemTask.status == status)
    if task_type:
        query = query.filter(SystemTask.task_type == task_type)
    
    if is_scheduler is True:
        # 반복 작업 (Cron 또는 Interval이 있는 경우)
        query = query.filter((SystemTask.cron_expression.is_not(None)) | (SystemTask.repeat_interval.is_not(None)))
    elif is_scheduler is False:
        # 단발성 작업
        query = query.filter(SystemTask.cron_expression.is_(None), SystemTask.repeat_interval.is_(None))
        
    total = query.count()
    tasks = query.order_by(desc(SystemTask.created_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "tasks": tasks
    }

@router.post("")
def create_task(
    task_in: SystemTaskCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write)
):
    """[관리자용] 새로운 비동기 태스크를 수동으로 등록합니다."""
    new_task = SystemTask(
        **task_in.model_dump(),
        created_by=admin.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # 📜 [보안 감사로그]: 태스크 수동 등록 기록
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
        metadata={"task_id": new_task.id, "task_type": new_task.task_type}
    )

    return new_task

@router.get("/{task_id}")
def get_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_read)
):
    """특정 태스크의 상세 정보(에러 로그 포함)를 조회합니다."""
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    return task

@router.post("/{task_id}/retry")
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write)
):
    """
    실패한 태스크를 강제로 다시 실행 대기(PENDING) 상태로 만듭니다.
    """
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    
    # 상태를 다시 PENDING으로 돌리고 시도 횟수를 초기화합니다.
    task.status = "PENDING"
    task.retry_count = 0
    task.error_log = f"[관리자 {admin.username}에 의해 재시도됨] {task.error_log or ''}"
    task.scheduled_at = datetime.now() # 지금 즉시 재시도
    
    db.commit()

    # 📜 [보안 감사로그]: 실패 태스크 관리자 수동 재시도 기록
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
        message=f"실패했던 작업 #{task.id} ({task.task_type})을 PENDING 상태로 재투입했습니다.",
        metadata={"task_id": task.id, "task_type": task.task_type}
    )

    return {"message": "태스크가 다시 큐에 등록되었습니다.", "task_id": task.id}


@router.put("/{task_id}")
def update_task(
    task_id: int,
    task_in: SystemTaskUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write)
):
    """
    [관리자용] 대기 중(PENDING)인 비동기/예약 태스크의 스케줄, 주기 및 옵션을 수정합니다.
    """
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")

    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="현재 실행 중(RUNNING)인 작업은 수정할 수 없습니다.")

    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    # cron_expression 또는 repeat_interval이 갱신되었고 scheduled_at이 명시되지 않은 경우 다음 스케줄 일시 재계산
    if ("cron_expression" in update_data or "repeat_interval" in update_data) and "scheduled_at" not in update_data:
        from domain.system.task_service import calculate_next_scheduled_at
        re_next = calculate_next_scheduled_at(
            cron_expr=task.cron_expression,
            interval_sec=task.repeat_interval
        )
        if re_next:
            task.scheduled_at = re_next

    db.commit()
    db.refresh(task)

    # 📜 [보안 감사로그]: 태스크 스케줄 수정 기록
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
        metadata={"task_id": task.id, "task_type": task.task_type, "updated_fields": list(update_data.keys())}
    )

    return task


@router.delete("/failed/clear")
def clear_all_failed_tasks(
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write)
):
    """[관리자용] 실패(FAILED) 상태인 모든 고아 태스크를 일괄 영구 삭제합니다."""
    failed_tasks = db.query(SystemTask).filter(SystemTask.status == "FAILED").all()
    count = len(failed_tasks)
    if count == 0:
        return {"message": "삭제할 실패 태스크가 없습니다.", "deleted_count": 0}

    for t in failed_tasks:
        db.delete(t)
    db.commit()

    # 📜 [보안 감사로그]: 실패 태스크 일괄 정리 기록
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="SECURITY",
        severity="INFO",
        action="FAILED_TASKS_CLEARED",
        title=f"관리자({admin.username})에 의한 실패 태스크 {count}건 일괄 영구 삭제",
        user=admin,
        resource_type="system_task",
        resource_id="ALL_FAILED",
        message=f"FAILED 상태 고아 태스크 {count}건 영구 정리 완료",
        metadata={"deleted_count": count}
    )

    return {"message": f"실패한 태스크 {count}건이 일괄 삭제되었습니다.", "deleted_count": count}


@router.delete("/{task_id}")
def cancel_or_delete_task(
    task_id: int,
    hard_delete: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(check_task_write)
):
    """
    태스크를 취소하거나 영구 삭제합니다.
    - 실행 중(RUNNING)인 태스크는 삭제할 수 없습니다.
    - hard_delete=True 이거나 이미 FAILED/CANCELLED 인 경우 DB에서 영구 삭제합니다.
    """
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    
    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="이미 실행 중인 태스크는 삭제/취소할 수 없습니다.")
        
    is_hard = hard_delete or task.status in ("FAILED", "CANCELLED")
    action_name = "TASK_DELETED" if is_hard else "TASK_CANCELLED"
    msg = f"태스크 #{task.id} 영구 삭제" if is_hard else f"태스크 #{task.id} 취소"

    if is_hard:
        db.delete(task)
    else:
        task.status = "CANCELLED"
    db.commit()

    # 📜 [보안 감사로그]: 태스크 취소/삭제 기록
    safe_log_audit(
        db=db,
        app_id="tasks",
        log_type="SECURITY",
        severity="WARN",
        action=action_name,
        title=f"관리자({admin.username})에 의한 {msg}",
        user=admin,
        resource_type="system_task",
        resource_id=str(task_id),
        message=f"작업 #{task_id} ({task.task_type}) {msg} 완료",
        metadata={"task_id": task_id, "task_type": task.task_type, "hard_delete": is_hard}
    )

    return {"message": f"{msg} 완료되었습니다.", "task_id": task_id, "hard_deleted": is_hard}
