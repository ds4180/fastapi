from datetime import datetime
from sqlalchemy.orm import Session
from models import Alert, User
from domain.alert.alert_schema import AlertCreate

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

def create_alert(db: Session, alert_create: AlertCreate, user: User):
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
    return db_alert

def delete_alert(db: Session, db_alert: Alert):
    db.delete(db_alert)
    db.commit()

def get_alert(db: Session, alert_id: int):
    return db.query(Alert).filter(Alert.id == alert_id).first()

def toggle_alert(db: Session, db_alert: Alert):
    db_alert.is_active = not db_alert.is_active
    db.commit()
    return db_alert
