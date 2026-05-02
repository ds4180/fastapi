from fastapi import BackgroundTasks
from datetime import datetime
from sqlalchemy.orm import Session
from models import Alert, User
from domain.alert.alert_schema import AlertCreate, AlertUpdate

def get_alert_list(db: Session):
    return db.query(Alert).order_by(Alert.create_date.desc()).all()

def get_active_alerts(db: Session):
    now = datetime.now()
    alerts = db.query(Alert).filter(
        Alert.is_active == True,
        (Alert.start_date == None) | (Alert.start_date <= now),
        (Alert.end_date == None) | (Alert.end_date >= now)
    ).all()
    
    # DB 마이그레이션이 안 되었을 경우를 대비해 객체에 기본값 주입
    for a in alerts:
        if not hasattr(a, 'position') or a.position is None:
            a.position = 'top'
    return alerts

from domain.ws.ws_service import manager


async def create_alert(db: Session, alert_create: AlertCreate, user: User, background_tasks: BackgroundTasks):
    db_alert = Alert(
        message=alert_create.message,
        level=alert_create.level,
        style=alert_create.style,
        position=alert_create.position or 'top', # 기본값 보장
        route=alert_create.route,
        redirect_url=alert_create.redirect_url,
        start_date=alert_create.start_date,
        end_date=alert_create.end_date,
        target_users=alert_create.target_users,
        confirm_text=alert_create.confirm_text,
        reset_sec=alert_create.reset_sec,
        create_date=datetime.now(),
        user=user
    )
    db.add(db_alert)
    db.commit()
    
    # 🔔 실시간 웹소켓 알림 전송 (새 알림이 있음을 모든 클라이언트에 알림)
    # 기존 코드의 방식대로 백그라운드 태스크를 활용할 수 있게 연결
    background_tasks.add_task(manager.broadcast, {"type": "new_alert"})
        
    return db_alert


def delete_alert(db: Session, db_alert: Alert):
    db.delete(db_alert)
    db.commit()

def get_alert(db: Session, alert_id: int):
    return db.query(Alert).filter(Alert.id == alert_id).first()

async def toggle_alert(db: Session, db_alert: Alert):
    db_alert.is_active = not db_alert.is_active
    db.commit()
    
    # 활성 상태가 변경되었으므로 갱신 신호 발송
    try:
        await manager.broadcast({"type": "new_alert"})
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        
    return db_alert

def update_alert(db: Session, db_alert: Alert, alert_update: AlertUpdate):
    for key, value in alert_update.model_dump(exclude_unset=True).items():
        setattr(db_alert, key, value)
    db.commit()
    db.refresh(db_alert)
    return db_alert
