from fastapi import APIRouter, Body, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from database import get_db
from core.audit import safe_log_audit
from core.deps import require_app_permission
from domain.user.user_router import get_current_user # To get current user and its ID
from . import schemas # Assuming schemas.py will define PushSubscriptionCreate
from . import push_service # Now importing the service
from models import User # To use models.User for Depends(get_current_user)

router = APIRouter(prefix="/push", tags=["Push Notifications"]) # Changed tag to active

check_push_read = require_app_permission("pushs", action="read")
check_push_write = require_app_permission("pushs", action="write")


@router.get("/options", status_code=status.HTTP_200_OK)
def get_push_domain_options(
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_read),
):
    """도메인별 Web Push 자동 발송 옵션을 조회합니다."""
    return {"options": push_service.get_push_domain_options(db)}


@router.put("/options", status_code=status.HTTP_200_OK)
def update_push_domain_options(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_write),
):
    """도메인별 Web Push 자동 발송 옵션을 저장합니다."""
    raw_options = payload.get("options") if isinstance(payload.get("options"), dict) else payload
    updated = push_service.update_push_domain_options(db, raw_options)
    safe_log_audit(
        db=db,
        app_id="pushs",
        log_type="CHANGE",
        action="PUSH_DOMAIN_OPTIONS_UPDATE",
        title="도메인별 Web Push 발송 옵션 변경",
        user=admin,
        resource_type="system_config",
        resource_id=push_service.PUSH_DOMAIN_OPTIONS_KEY,
        message=f"관리자 '{admin.username}'이(가) 도메인 푸시 옵션을 변경했습니다.",
    )
    return {"message": "saved", "options": updated}

# Endpoint to subscribe to push notifications
@router.post("/subscribe", status_code=status.HTTP_200_OK)
def subscribe_push_notification(
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
    saved_subscription = push_service.save_subscription(
        db, subscription_data, user_id=current_user.id
    )
    safe_log_audit(
        db=db,
        app_id="pushs",
        log_type="CHANGE",
        action="PUSH_SUBSCRIBE",
        title="푸시 알림 구독 등록",
        user=current_user,
        resource_type="push_subscription",
        resource_id=str(saved_subscription.id),
    )
    return {"message": "Subscription successful", "status": "active", "id": saved_subscription.id}


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
def unsubscribe_push_notification(
    payload: schemas.PushUnsubscribeRequest,
    db: Session = Depends(get_db),
):
    """
    로그아웃 또는 세션 종료 시 해당 기기(endpoint)의 푸시 알림 구독을 DB에서 제거합니다.
    (쿠키 만료 직후에도 안전하게 호출될 수 있도록 고유 endpoint 기반으로 삭제)
    """
    deleted_count = push_service.delete_subscription_by_endpoint(db, payload.endpoint)
    return {"message": "Unsubscribed successfully", "deleted": deleted_count}

# Endpoint to send push notifications to all subscribers
@router.post("/send-all", status_code=status.HTTP_200_OK)
def send_all_push_notifications(
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
        
    result = push_service.send_to_all_subscribers(db)
    safe_log_audit(
        db=db,
        app_id="pushs",
        log_type="CHANGE",
        action="PUSH_BROADCAST",
        title=f"전체 푸시 알림 발송 ({result.get('sent', 0)}건)",
        user=current_user,
        resource_type="pushs",
        message=f"관리자 '{current_user.username}'이(가) 전체 푸시 알림을 발송했습니다. (발송: {result.get('sent', 0)}건)",
    )
    return {"message": "Broadcast initiated", "sent": result.get("sent", 0)}