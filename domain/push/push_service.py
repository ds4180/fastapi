from sqlalchemy.orm import Session, joinedload
from models import PushSubscription, User, UserProfile
from . import schemas
from pywebpush import webpush, WebPushException
from typing import Iterable, Optional, Callable, Any
import json
import os
import threading
import logging
from database import SessionLocal

logger = logging.getLogger("push_service")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "4pEtY2AYOArlBnYTWlv8-w8pRS21VhiQCZHD2rwUH74")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_SUBJECT", "mailto:admin@jeju.live")}
WEBPUSH_TIMEOUT_SEC = int(os.getenv("WEBPUSH_TIMEOUT_SEC", "10"))


def get_subscription_by_endpoint(db: Session, endpoint: str):
    return db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()


def get_all_subscriptions(db: Session):
    return db.query(PushSubscription).all()


def save_subscription(db: Session, subscription_data: schemas.PushSubscriptionCreate, user_id: int):
    existing_sub = get_subscription_by_endpoint(db, subscription_data.endpoint)

    if existing_sub:
        # ⚡ [자원 최적화] 기존 DB 레코드와 소유자(user_id) 및 암호화 키가 완전히 동일하면 불필요한 DB Write(commit)를 생략합니다.
        if (
            existing_sub.user_id == user_id
            and existing_sub.p256dh == subscription_data.keys.p256dh
            and existing_sub.auth == subscription_data.keys.auth
        ):
            return existing_sub

        # 공용 기기에서 다른 사원이 로그인했거나 키가 갱신된 경우에만 Upsert Commit 수행
        existing_sub.user_id = user_id
        existing_sub.p256dh = subscription_data.keys.p256dh
        existing_sub.auth = subscription_data.keys.auth
        db.commit()
        db.refresh(existing_sub)
        return existing_sub

    new_sub = PushSubscription(
        user_id=user_id,
        endpoint=subscription_data.endpoint,
        p256dh=subscription_data.keys.p256dh,
        auth=subscription_data.keys.auth,
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
    return new_sub


def delete_subscription_by_endpoint(db: Session, endpoint: str) -> int:
    """
    로그아웃 시 해당 기기 브라우저의 푸시 엔드포인트를 DB 발송 명단에서 즉시 제거합니다.
    """
    deleted = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == endpoint)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def _build_push_payload(title: str, body: str, url: str = "/") -> str:
    return json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/favicon.png",
        "badge": "/favicon.png",
    }, ensure_ascii=False)


def _dispatch_push(db: Session, subscriptions: list, title: str, body: str, url: str = "/") -> dict:
    """
    [공통 Web Push 발송 및 만료 구독(404/410) 자동 정리기]
    """
    if not subscriptions:
        return {"sent": 0, "failed": 0, "cleaned": 0}

    payload = _build_push_payload(title, body, url)
    sent = 0
    failed = 0
    expired_ids: list[int] = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS,
                timeout=WEBPUSH_TIMEOUT_SEC,
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (404, 410) and getattr(sub, "id", None) is not None:
                expired_ids.append(sub.id)
            else:
                logger.warning(f"WebPush 실패 ({sub.endpoint}): {e}")
        except Exception as e:
            failed += 1
            logger.warning(f"Push 예외 ({sub.endpoint}): {e}")

    cleaned = 0
    if expired_ids:
        try:
            cleaned = (
                db.query(PushSubscription)
                .filter(PushSubscription.id.in_(expired_ids))
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.info(f"🧹 [PushService] 만료된 구독 {cleaned}건 자동 정리 완료")
        except Exception as e:
            db.rollback()
            logger.warning(f"만료 구독 정리 실패: {e}")

    return {"sent": sent, "failed": failed, "cleaned": cleaned}


def dispatch_push_async(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """HTTP 요청 응답을 블로킹하지 않고 데몬 스레드에서 푸시 발송을 실행합니다."""
    def _runner():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning(f"비동기 푸시 발송 오류: {e}")

    threading.Thread(target=_runner, daemon=True).start()


def send_to_all_subscribers(db: Session):
    all_subscriptions = get_all_subscriptions(db)
    return _dispatch_push(
        db,
        all_subscriptions,
        "새로운 알림!",
        "모든 구독자에게 보내는 테스트 메시지입니다.",
        "/",
    )


def send_push_to_all(title: str, body: str, url: str = "/", db: Session = None):
    """
    [v2.2] 모든 구독자에게 정규화된 JSON 푸시 발송 (만료 구독 자동 정리 포함)
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        subscriptions = db.query(PushSubscription).all()
        return _dispatch_push(db, subscriptions, title, body, url)
    finally:
        if own_session:
            db.close()


def send_push_to_user(user_id: int, title: str, body: str, url: str = "/", db: Session = None):
    """
    [특정 사용자 타겟 Web Push 발송]
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
        if not subscriptions:
            return {"sent": 0, "failed": 0, "cleaned": 0, "reason": "no_subscriptions"}
        return _dispatch_push(db, subscriptions, title, body, url)
    finally:
        if own_session:
            db.close()


def send_push_to_users(
    user_ids: Iterable[int],
    title: str,
    body: str,
    url: str = "/",
    db: Session = None,
):
    """
    [다중 사용자 타겟 Web Push 일괄 발송]
    """
    ids = [int(uid) for uid in set(user_ids) if uid is not None]
    if not ids:
        return {"sent": 0, "failed": 0, "cleaned": 0}

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id.in_(ids)).all()
        return _dispatch_push(db, subscriptions, title, body, url)
    finally:
        if own_session:
            db.close()


def send_push_to_rank(
    min_rank: int,
    title: str,
    body: str,
    url: str = "/",
    exclude_user_id: Optional[int] = None,
    db: Session = None,
):
    """
    [최소 랭크 기준 타겟 Web Push 발송]
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        q = (
            db.query(PushSubscription)
            .join(User, PushSubscription.user_id == User.id)
            .join(UserProfile, User.id == UserProfile.user_id)
            .filter(UserProfile.is_active == True, UserProfile.rank_level >= int(min_rank))
        )
        if exclude_user_id is not None:
            q = q.filter(PushSubscription.user_id != int(exclude_user_id))
        subscriptions = q.all()
        return _dispatch_push(db, subscriptions, title, body, url)
    finally:
        if own_session:
            db.close()


def is_push_option_enabled(options: Any, key: str, default: bool = False) -> bool:
    """
    [공용 옵션 플래그 판독기]
    BoardConfig.options / AppRegistry.config_schema 등의 JSON 옵션에서
    단순 bool 또는 { "value": bool } 형태를 일관되게 판별합니다.
    """
    if not isinstance(options, dict) or key not in options:
        return default
    raw = options.get(key)
    if isinstance(raw, dict):
        return bool(raw.get("value", default))
    return bool(raw)


def _filter_allowed_subscriptions(
    db: Session,
    predicate: Callable[[User], bool],
    exclude_user_id: Optional[int] = None,
) -> list:
    """활성 사용자 중 predicate(user)를 만족하는 구독 목록만 필터링합니다."""
    q = db.query(PushSubscription)
    if exclude_user_id is not None:
        q = q.filter(PushSubscription.user_id != int(exclude_user_id))
    subs = q.all()
    if not subs:
        return []

    user_ids = {s.user_id for s in subs if s.user_id is not None}
    if not user_ids:
        return []

    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(User.id.in_(user_ids))
        .all()
    )
    allowed_user_ids = {
        u.id
        for u in users
        if (u.profile is None or u.profile.is_active is not False) and predicate(u)
    }
    return [s for s in subs if s.user_id in allowed_user_ids]


def send_push_to_groups(
    groups: Iterable[str],
    title: str,
    body: str,
    url: str = "/",
    exclude_user_id: Optional[int] = None,
):
    """
    [특정 그룹(주그룹/부그룹) 소속 구독자 대상 Web Push 발송]
    """
    from core.permission import get_user_groups

    target_groups = {str(g) for g in groups if g}
    if not target_groups:
        return {"sent": 0, "failed": 0, "cleaned": 0}

    with SessionLocal() as db:
        target_subs = _filter_allowed_subscriptions(
            db,
            lambda u: bool(get_user_groups(u) & target_groups),
            exclude_user_id=exclude_user_id,
        )
        return _dispatch_push(db, target_subs, title, body, url)


def send_push_to_app_users(
    app_id: str,
    title: str,
    body: str,
    url: str = "/",
    action: str = "read",
    exclude_user_id: Optional[int] = None,
):
    """
    [AppRegistry 4단계 권한(can_access_app) 충족 구독자 대상 범용 푸시 발송]
    - 배차, 휴무, 블랙박스 등 어떤 도메인 앱에서도 app_id만 넘겨 권한자에게 즉시 발송할 수 있습니다.
    """
    from models import AppRegistry
    from core.permission import can_access_app

    with SessionLocal() as db:
        app_obj = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
        if not app_obj:
            return {"sent": 0, "failed": 0, "cleaned": 0}

        target_subs = _filter_allowed_subscriptions(
            db,
            lambda u: can_access_app(user=u, app_obj=app_obj, action=action),
            exclude_user_id=exclude_user_id,
        )
        return _dispatch_push(db, target_subs, title, body, url)


def send_push_to_board_readers(
    board_id: int,
    title: str,
    body: str,
    url: str = "/",
    exclude_user_id: Optional[int] = None,
):
    """
    [게시판 4단계 열람 권한(can_access_board) 충족 구독자 대상 비동기 푸시 발송]
    """
    from models import BoardConfig
    from core.permission import can_access_board

    with SessionLocal() as db:
        board = db.query(BoardConfig).filter(BoardConfig.id == board_id).first()
        if not board:
            return {"sent": 0, "failed": 0, "cleaned": 0}

        target_subs = _filter_allowed_subscriptions(
            db,
            lambda u: can_access_board(u, board, action="read"),
            exclude_user_id=exclude_user_id,
        )
        return _dispatch_push(db, target_subs, title, body, url)


PUSH_DOMAIN_OPTIONS_KEY = "PUSH_DOMAIN_OPTIONS"
DEFAULT_PUSH_DOMAIN_OPTIONS = {
    "dispatch_confirmed": True,
    "dayoff_request": True,
    "dayoff_result": True,
    "blackbox_request": True,
    "alert_instruction": True,
    "survey_request": True,
}


def get_push_domain_options(db: Session) -> dict:
    """
    [도메인별 Web Push 발송 옵션 조회]
    SystemConfig('PUSH_DOMAIN_OPTIONS')를 읽어 기본값과 병합해 반환합니다.
    """
    from models import SystemConfig

    merged = dict(DEFAULT_PUSH_DOMAIN_OPTIONS)
    row = db.query(SystemConfig).filter(SystemConfig.key == PUSH_DOMAIN_OPTIONS_KEY).first()
    if row and isinstance(row.value, dict):
        for k in DEFAULT_PUSH_DOMAIN_OPTIONS:
            if k in row.value:
                merged[k] = bool(row.value[k])
    return merged


def update_push_domain_options(db: Session, options: dict) -> dict:
    """
    [도메인별 Web Push 발송 옵션 저장]
    허용된 키만 정규화하여 SystemConfig('PUSH_DOMAIN_OPTIONS')에 저장합니다.
    """
    from models import SystemConfig

    merged = get_push_domain_options(db)
    if isinstance(options, dict):
        for k in DEFAULT_PUSH_DOMAIN_OPTIONS:
            if k in options:
                merged[k] = bool(options[k])

    row = db.query(SystemConfig).filter(SystemConfig.key == PUSH_DOMAIN_OPTIONS_KEY).first()
    if row:
        row.value = merged
    else:
        db.add(
            SystemConfig(
                key=PUSH_DOMAIN_OPTIONS_KEY,
                value=merged,
                description="도메인별 Web Push 자동 발송 ON/OFF 설정",
            )
        )
    db.commit()
    return merged


def is_push_domain_enabled(db: Session, key: str) -> bool:
    """특정 도메인 푸시 옵션의 활성화 여부를 반환합니다."""
    return bool(get_push_domain_options(db).get(key, False))
