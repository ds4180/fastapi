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
