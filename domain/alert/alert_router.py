"""
============================================================================
[사내 전역 공지 및 업무 지시 알림 API 라우터 (domain/alert/alert_router.py)]
============================================================================

💡 이 파일의 역할:
운영 관리자가 사내 임직원에게 업무 지시 및 공지사항(토스트, 배너, 모달)을 전송하고
관리하는 엔드포인트를 제공합니다.

🌟 코어 보안 강화 (리팩토링 반영):
1. `core.deps`의 `RankChecker`를 도입하여 비인가자의 무단 알림 생성/수정/삭제를 100% 차단합니다.
2. 관리자 등급(Rank >= 8 또는 root 9)만 공지를 등록/편집/삭제할 수 있도록 인가 규칙을 통일했습니다.
3. 활성 알림 조회(`GET /alert/active`)는 일반 유저 및 손님도 안전하게 조회할 수 있도록 분리했습니다.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from starlette import status
from typing import Optional

from database import get_db
from domain.alert import alert_schema, alert_crud
from core.deps import get_current_user, get_current_user_optional, require_app_permission
from models import User

router = APIRouter(
    prefix="/alert",
    tags=["Alert"]
)

# 🔒 관리자 권한 의존성 정의 (AppRegistry 실시간 4단계 인가 가드와 완전 연동)
check_alerts_read = require_app_permission("admin_alerts", action="read")
check_alerts_write = require_app_permission("admin_alerts", action="write")


@router.get("/list", response_model=list[alert_schema.Alert])
def alert_list(
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_read)
):
    """
    모든 알림 목록 조회 (관리자 전용)
    - 만료되거나 비활성화된 알림을 포함한 전체 히스토리를 반환합니다.
    """
    return alert_crud.get_alert_list(db)


@router.get("/active", response_model=list[alert_schema.Alert])
def active_alert_list(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    현재 활성화된 알림 목록 조회 (일반 사용자 및 클라이언트용)
    - 기간 내에 있고 활성화된 알림만 반환합니다.
    """
    return alert_crud.get_active_alerts(db, user=current_user)


@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=alert_schema.Alert)
async def alert_create(
    _alert_create: alert_schema.AlertCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_write)
):
    """
    새로운 알림 생성 (관리자 전용)
    - Level 5(긴급/시스템 락) 알림인 경우 전 사용자에게 백그라운드 Web Push를 자동 발송합니다.
    - 실시간 WebSocket으로 클라이언트에 즉시 갱신 신호를 브로드캐스트합니다.
    """
    return await alert_crud.create_alert(
        db,
        alert_create=_alert_create,
        user=admin_user,
        background_tasks=background_tasks
    )


@router.delete("/delete/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def alert_delete(
    alert_id: int, 
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_write)
):
    """
    알림 삭제 (관리자 전용)
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")
    
    alert_crud.delete_alert(db, db_alert)


@router.put("/update/{alert_id}", response_model=alert_schema.Alert)
async def alert_update(
    alert_id: int, 
    _alert_update: alert_schema.AlertUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_write)
):
    """
    알림 수정 (관리자 전용)
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")
    
    return alert_crud.update_alert(db, db_alert=db_alert, alert_update=_alert_update)


@router.post("/toggle/{alert_id}", response_model=alert_schema.Alert)
async def alert_toggle(
    alert_id: int, 
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_write)
):
    """
    알림 활성/비활성 상태 전환 (관리자 전용)
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")
    
    return await alert_crud.toggle_alert(db, db_alert)


@router.get("/{alert_id}/acknowledgements")
def alert_acknowledgements(
    alert_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(check_alerts_read)
):
    """
    [관리자 전용] 특정 알림/지시사항의 사원별 수신 확인 현황 및 통계 조회
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")

    return alert_crud.get_alert_acknowledgements(db, alert_id)

