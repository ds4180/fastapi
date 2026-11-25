"""
[푸시 알림 구독 관리자 라우터 (domain/push/push_admin_router.py)]
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from database import get_db
from core.deps import require_app_permission
from domain.push.push_service import send_push_to_all
from models import User

router = APIRouter(tags=["Admin Push"])

check_push_admin = require_app_permission("pushs", action="read")
check_push_admin_write = require_app_permission("pushs", action="write")


@router.get("/push/subscriptions")
def list_push_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin),
):
    """모든 푸시 구독 목록 조회 (관리자용 - 기기/브라우저 유형 및 소속 그룹 상세 포함)"""
    subs = (
        db.query(models.PushSubscription)
        .join(models.User, models.PushSubscription.user_id == models.User.id)
        .all()
    )
    result = []
    for s in subs:
        user = db.query(models.User).filter(models.User.id == s.user_id).first()
        profile = user.profile if user else None

        ep_lower = (s.endpoint or "").lower()
        if "fcm.googleapis.com" in ep_lower or "google" in ep_lower:
            browser_type = "Chrome / Android"
            browser_icon = "mdi:google-chrome"
            badge_color = "bg-blue-50 text-blue-700 border-blue-200"
        elif "mozilla" in ep_lower or "firefox" in ep_lower:
            browser_type = "Firefox"
            browser_icon = "mdi:firefox"
            badge_color = "bg-amber-50 text-amber-700 border-amber-200"
        elif "apple" in ep_lower or "safari" in ep_lower:
            browser_type = "Safari / iOS"
            browser_icon = "mdi:apple-safari"
            badge_color = "bg-purple-50 text-purple-700 border-purple-200"
        elif "microsoft" in ep_lower or "edge" in ep_lower:
            browser_type = "Microsoft Edge"
            browser_icon = "mdi:microsoft-edge"
            badge_color = "bg-cyan-50 text-cyan-700 border-cyan-200"
        else:
            browser_type = "Web Push Standard"
            browser_icon = "mdi:cellphone-wireless"
            badge_color = "bg-slate-50 text-slate-700 border-slate-200"

        result.append(
            {
                "id": s.id,
                "user_id": s.user_id,
                "username": user.username if user else "Unknown",
                "real_name": (user.real_name if user and user.real_name else "")
                or (user.username if user else ""),
                "primary_group": profile.primary_group if profile and profile.primary_group else "소속 미정",
                "rank_level": profile.rank_level if profile else 0,
                "endpoint": s.endpoint,
                "endpoint_preview": s.endpoint[:75] + "..." if len(s.endpoint) > 75 else s.endpoint,
                "browser_type": browser_type,
                "browser_icon": browser_icon,
                "badge_color": badge_color,
            }
        )
    return result


@router.post("/push/send")
def admin_send_push(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write),
):
    """관리자가 커스텀 메시지를 전체 푸시 발송"""
    title = payload.get("title", "공지사항")
    body = payload.get("body", "")

    if not body:
        raise HTTPException(status_code=400, detail="메시지 본문을 입력해주세요.")

    result = send_push_to_all(title, body, db=db)
    return {"message": "success", "sent_count": result.get("sent", 0)}


@router.delete("/push/subscriptions")
def delete_all_push_subscriptions(
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write),
):
    """전체 푸시 구독 기기 목록 일괄 초기화(전체 삭제)"""
    deleted_count = db.query(models.PushSubscription).delete(synchronize_session=False)
    db.commit()
    return {"message": "success", "deleted_count": deleted_count}


@router.delete("/push/subscriptions/{sub_id}")
def delete_push_subscription(
    sub_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_push_admin_write),
):
    """무효한 푸시 구독 정보 강제 삭제"""
    sub = db.query(models.PushSubscription).filter(models.PushSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")
    db.delete(sub)
    db.commit()
    return {"message": "success"}
