from sqlalchemy.orm import Session
from models import PushSubscription, User # User might not be directly used here, but good to have if needed for relations
from . import schemas # Import schemas for type hinting
from pywebpush import webpush, WebPushException # Import webpush library

# TODO: Configure these securely, preferably via environment variables
# For now, using placeholder values. Replace with your actual VAPID keys and email.
VAPID_PRIVATE_KEY = "4pEtY2AYOArlBnYTWlv8-w8pRS21VhiQCZHD2rwUH74"
VAPID_CLAIMS = {"sub": "mailto:admin@jeju.live"}

def get_subscription_by_endpoint(db: Session, endpoint: str):
    return db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()

def get_all_subscriptions(db: Session):
    return db.query(PushSubscription).all()

async def save_subscription(db: Session, subscription_data: schemas.PushSubscriptionCreate, user_id: int):
    # Check if subscription already exists (endpoint is unique)
    existing_sub = get_subscription_by_endpoint(db, subscription_data.endpoint)

    if existing_sub:
        # If exists, update its details or just return it if no changes
        # For simplicity, if it exists, we just return it. In a real app, you might update p256dh, auth.
        print("Service: Subscription already exists, returning existing one.")
        return existing_sub
    
    new_sub = PushSubscription(
        user_id=user_id,
        endpoint=subscription_data.endpoint,
        p256dh=subscription_data.keys.p256dh,
        auth=subscription_data.keys.auth
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    print("Service: New subscription saved successfully.")
    return new_sub

import json
from database import SessionLocal # 백그라운드 태스크 및 관리자용 세션 생성을 위해 추가

async def send_to_all_subscribers(db: Session):
    print("Service: Attempting to send notifications to all subscribers.")
    all_subscriptions = get_all_subscriptions(db)
    
    sent_count = 0
    failed_count = 0
    
    notification_payload = "{\"title\": \"새로운 알림!\", \"body\": \"모든 구독자에게 보내는 테스트 메시지입니다.\", \"icon\": \"/favicon.png\"}"
    
    for sub in all_subscriptions:
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=notification_payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            sent_count += 1
            print(f"Successfully sent push to {sub.endpoint}")
        except WebPushException as e:
            failed_count += 1
            print(f"Failed to send push to {sub.endpoint}: {e}")
            # Consider deleting invalid subscriptions from DB
        except Exception as e:
            failed_count += 1
            print(f"An unexpected error occurred sending push to {sub.endpoint}: {e}")
            
    print(f"Service: Finished sending. Sent: {sent_count}, Failed: {failed_count}.")
    return {"sent": sent_count, "failed": failed_count}

def send_push_to_all(title: str, body: str, url: str = "/", db: Session = None):
    """
    [v2.1 리팩토링] 모든 구독자에게 정규화된 JSON 푸시 발송
    - title, body 뿐만 아니라 클릭 시 이동할 url 정보를 포함합니다.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
        
    try:
        subscriptions = db.query(PushSubscription).all()
        # 🔗 서비스 워커(sw.js) 파서 규격에 맞춘 JSON 페이로드 생성
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/favicon.png",
            "badge": "/favicon.png"
        })

        sent = 0
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint, 
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS
                )
                sent += 1
            except Exception as e:
                print(f"Push failed for {sub.endpoint}: {e}")
        return {"sent": sent}
    finally:
        if own_session:
            db.close()
