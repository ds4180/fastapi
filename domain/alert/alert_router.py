from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette import status

from database import get_db
from domain.alert import alert_schema, alert_crud
from domain.user.user_router import get_current_user
from models import User

router = APIRouter(
    prefix="/alert",
)

@router.get("/list", response_model=list[alert_schema.Alert])
def alert_list(db: Session = Depends(get_db)):
    """
    모든 알림 목록 조회 (관리자용)
    """
    return alert_crud.get_alert_list(db)

@router.get("/active", response_model=list[alert_schema.Alert])
def active_alert_list(db: Session = Depends(get_db)):
    """
    현재 활성화된 알림 목록 조회 (사용자용)
    """
    return alert_crud.get_active_alerts(db)

@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=alert_schema.Alert)
async def alert_create(_alert_create: alert_schema.AlertCreate,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """
    새로운 알림 생성
    """
    # TODO: 임시로 모든 로그인 유저가 생성 가능하게 함. 나중에 관리자 권한 체크 추가 필요.
    return await alert_crud.create_alert(db, alert_create=_alert_create, user=current_user)

@router.delete("/delete/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def alert_delete(alert_id: int, 
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """
    알림 삭제
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")
    
    # TODO: 관리자 권한 체크 필요
    alert_crud.delete_alert(db, db_alert)

@router.post("/toggle/{alert_id}", response_model=alert_schema.Alert)
async def alert_toggle(alert_id: int, 
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """
    알림 활성/비활성 상태 전환
    """
    db_alert = alert_crud.get_alert(db, alert_id)
    if not db_alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다.")
    
    return alert_crud.toggle_alert(db, db_alert)
