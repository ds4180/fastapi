from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import SystemTask, User
from domain.user.user_router import check_rank
from datetime import datetime
from typing import List, Optional
from .admin_schema import SystemTaskCreate

router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin_tasks"]
)

# 최고 관리자(Rank 4)만 접근 가능하도록 설정
check_admin = check_rank(required_rank=4)

@router.get("/types")
def list_task_types(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """[관리자용] 현재 시스템에 등록된 모든 태스크 유형과 가이드를 조회합니다."""
    from domain.system.task_worker import TASK_HANDLERS
    
    # 작업 유형별 예시 페이로드 (간단한 정의)
    guidelines = {
        "MEDIA_ISOLATE": {"file_path": "/path/to/file", "asset_id": 1},
        "THUMB_GEN": {"asset_id": 1},
        "MEDIA_BACKUP": {"asset_ids": [1, 2], "target_user_id": 1},
        "MEDIA_GC": {"indices": [1, 2, 3, 4, 5]}
    }
    
    return [{"type": t, "example": guidelines.get(t, {})} for t in TASK_HANDLERS.keys()]

@router.get("")
def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    is_scheduler: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
):
    """[관리자용] 새로운 비동기 태스크를 수동으로 등록합니다."""
    new_task = SystemTask(
        **task_in.model_dump(),
        created_by=admin.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@router.get("/{task_id}")
def get_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
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
    admin: User = Depends(check_admin)
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
    return {"message": "태스크가 다시 큐에 등록되었습니다.", "task_id": task.id}

@router.delete("/{task_id}")
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """실행 대기 중인 태스크를 취소 처리합니다."""
    task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    
    if task.status == "RUNNING":
        raise HTTPException(status_code=400, detail="이미 실행 중인 태스크는 취소할 수 없습니다.")
        
    task.status = "CANCELLED"
    db.commit()
    return {"message": "태스크가 취소되었습니다."}
