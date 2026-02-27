import os
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session
from models import PushSubscription
from database import SessionLocal

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@jeju.live")

def send_push_to_all(db: Session, message: str):
    """
    모든 구독자에게 웹 푸시 메시지를 발송합니다.
    """
    # 세션이 없으면 새로 생성하여 사용 (백그라운드 태스크 대응)
    is_internal_session = False
    if db is None:
        db = SessionLocal()
        is_internal_session = True

    try:
        subscriptions = db.query(PushSubscription).all()
        results = []
        
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                    },
                    data=message,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_SUBJECT}
                )
                results.append({"endpoint": sub.endpoint[:40], "status": "success"})
            except WebPushException as e:
                results.append({"endpoint": sub.endpoint[:40], "status": f"failed: {str(e)}"})
                
        return results
    finally:
        # 직접 생성한 세션일 경우에만 닫아줌
        if is_internal_session:
            db.close()
