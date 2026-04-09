from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from database import get_db
from domain.user.user_router import get_current_user # To get current user and its ID
from . import schemas # Assuming schemas.py will define PushSubscriptionCreate
from . import push_service # Now importing the service
from models import User # To use models.User for Depends(get_current_user)

router = APIRouter(prefix="/push", tags=["Push Notifications"]) # Changed tag to active

# Endpoint to subscribe to push notifications
@router.post("/subscribe", status_code=status.HTTP_200_OK)
async def subscribe_push_notification(
    subscription_data: schemas.PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Assuming current user is authenticated
):
    """
    새로운 푸시 알림 구독을 등록합니다.
    - 클라이언트로부터 받은 구독 정보를 데이터베이스에 저장합니다.
    - VAPID 키 교환 등의 로직이 필요할 수 있습니다.
    """
    # Pass user_id to the service function
    saved_subscription = await push_service.save_subscription(
        db, subscription_data, user_id=current_user.id
    )
    print(f"Received push subscription request for user {current_user.id}: {subscription_data.dict()}")
    return {"message": "Subscription successful", "status": "active", "id": saved_subscription.id}

# Endpoint to send push notifications to all subscribers
@router.post("/send-all", status_code=status.HTTP_200_OK)
async def send_all_push_notifications(
    db: Session = Depends(get_db),
    # Assuming only admin can send to all, requiring authentication
    current_user: User = Depends(get_current_user) 
):
    """
    등록된 모든 가입자에게 푸시 알림을 보냅니다.
    - 데이터베이스에서 모든 활성 푸시 구독 정보를 조회합니다.
    - 푸시 알림 라이브러리(예: pywebpush)를 사용하여 알림을 발송합니다.
    """
    # Add admin check for 'send-all'
    if current_user.rank() < 4: # Assuming rank 4 is admin
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다.")
        
    result = await push_service.send_to_all_subscribers(db)
    print("Received request to send push notifications to all!")
    return {"message": "Broadcast initiated", "sent": result.get("sent", 0)}