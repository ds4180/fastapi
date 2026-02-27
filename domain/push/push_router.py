import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import PushSubscription
from domain.push import push_service

router = APIRouter(prefix="/push", tags=["push"])

# 구독 정보 저장용 스키마
class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class SubscriptionRequest(BaseModel):
    endpoint: str
    keys: SubscriptionKeys

# 1. 구독 정보 저장 API (프론트에서 "알림 허용" 버튼 누를 때 호출)
@router.post("/subscribe")
def subscribe(sub: SubscriptionRequest, db: Session = Depends(get_db)):
    # 이미 저장된 endpoint면 그냥 통과, 없으면 새로 저장
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == sub.endpoint).first()
    if not existing:
        new_sub = PushSubscription(
            endpoint=sub.endpoint,
            p256dh=sub.keys.p256dh,
            auth=sub.keys.auth
        )
        db.add(new_sub)
        db.commit()
    return {"message": "구독 완료"}

# 2. 모든 구독자에게 푸시 알림 발송 API (관리자용 테스트)
@router.post("/send-all")
def send_all(db: Session = Depends(get_db)):
    results = push_service.send_push_to_all(db, "안녕하세요! 테스트 푸시 알림입니다. 🎉")
    return {"sent": len(results), "results": results}
