from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import get_db
from models import SystemTask, User
from domain.user.user_router import check_rank
from datetime import datetime
from typing import List, Optional

router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin_tasks"]
)

# 최고 관리자(Rank 4)만 접근 가능하도록 설정
check_admin = check_rank(required_rank=4)

@router.get("")
def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """
    [관리자용] 모든 비동기 태스크 목록을 조회합니다.
    최신순으로 정렬하며 상태나 타입으로 필터링이 가능합니다.
    """
    query = db.query(SystemTask)
    
    if status:
        query = query.filter(SystemTask.status == status)
    if task_type:
        query = query.filter(SystemTask.task_type == task_type)
        
    total = query.count()
    tasks = query.order_by(desc(SystemTask.created_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "tasks": tasks
    }

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
