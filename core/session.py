"""
============================================================================
[백엔드 실시간 세션 엔진 (core/session.py)]
============================================================================

💡 이 파일의 역할:
FastAPI 라우터에 섞여 있던 '멀티 디바이스 세션(DESKTOP/MOBILE)' 제어 로직을
독립된 엔진으로 캡슐화한 순수 비즈니스 서비스 모듈입니다.

🌟 주요 기능:
1. 클라이언트 User-Agent를 분석하여 기기 종류(MOBILE / DESKTOP)를 판별합니다.
2. 같은 기기에서 새 로그인이 발생하면 이전 세션을 강제 종료(KICKED_OUT)합니다.
3. 고유한 UUID 세션 키(JTI)를 발급하고, Redis Set 및 PostgreSQL에 안전하게 이중 저장합니다.
4. 요청이 올 때마다 세션 유효성을 검증하고, 슬라이딩 윈도우(만료 시간 자동 연장)를 적용합니다.
5. [v2.0 자가 치유]: Redis 재부팅 시 DB ACTIVE 세션을 바탕으로 키를 자동 복구(Self-Healing)하고,
   `joinedload`를 통해 단 1회의 쿼리로 User와 UserProfile을 일괄 로드합니다.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import Request
from sqlalchemy.orm import Session, joinedload
from redis.exceptions import RedisError
from redis_config import rd
from models import User, UserSession
from core.config import settings

logger = logging.getLogger("core.session")

# 📌 세션 유효 기간 (일 단위) - 중앙 설정소에서 가져옴
SESSION_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
SESSION_EXPIRE_SECONDS = 60 * 60 * 24 * SESSION_EXPIRE_DAYS

# 📌 DB 최근 활동 시각(last_activity) 갱신 최소 주기 (5분 = 300초)
# 매 API 요청마다 DB COMMIT을 수행하면 동시 요청 시 Row Lock 경합이 발생하므로,
# Redis 만료 시간은 매번 즉시 연장하되 DB 기록은 5분 주기로 스로틀링(Throttling)합니다.
ACTIVITY_UPDATE_INTERVAL_SECONDS = 300


def detect_device_category(user_agent: str) -> str:
    """
    User-Agent 헤더 문자열을 검사하여 MOBILE 또는 DESKTOP을 반환합니다.
    """
    ua = (user_agent or "").lower()
    if any(keyword in ua for keyword in ["mobi", "android", "iphone", "ipad"]):
        return "MOBILE"
    return "DESKTOP"


def create_user_session(db: Session, user: User, request: Request) -> str:
    """
    새로운 로그인 세션을 발급합니다.
    
    1. 동일한 기기 카테고리(예: 모바일)에서 이미 로그인되어 있던 기존 세션을
       모두 'KICKED_OUT(강제 로그아웃)' 처리하고 Redis에서 삭제합니다.
    2. 새로운 세션 고유 키(UUID)를 생성하여 Redis와 DB에 등록합니다.
    3. 생성된 세션 키(str)를 반환합니다.
    """
    user_agent = request.headers.get("user-agent", "")
    ip_address = request.client.host if request.client else "unknown"
    device_category = detect_device_category(user_agent)

    redis_key = f"session:{user.id}:{device_category}"

    # [1단계] 기존 세션이 있다면 DB에서 KICKED_OUT 처리 및 Redis에서 즉시 추방
    existing_jtis = rd.smembers(redis_key)
    for jti_item in existing_jtis:
        old_jti = jti_item.decode("utf-8") if isinstance(jti_item, bytes) else str(jti_item)
        db.query(UserSession).filter(UserSession.session_key == old_jti).update({
            "status": "KICKED_OUT",
            "logout_at": datetime.now()
        })
        rd.srem(redis_key, old_jti)
    db.commit()

    # [2단계] 새로운 고유 세션 키(JTI) 발급
    new_jti = str(uuid.uuid4())
    rd.sadd(redis_key, new_jti)
    rd.expire(redis_key, SESSION_EXPIRE_SECONDS)

    # [3단계] DB에 새로운 세션 기록 저장
    db_session = UserSession(
        user_id=user.id,
        session_key=new_jti,
        device_category=device_category,
        status="ACTIVE",
        device_name=user_agent[:200], # 너무 긴 UA는 자름
        ip_address=ip_address,
        login_at=datetime.now(),
        last_activity=datetime.now()
    )
    db.add(db_session)
    db.commit()

    return new_jti


def validate_session(db: Session, session_id: Optional[str]) -> Optional[User]:
    """
    세션 키의 유효성을 검증하고, 유효한 경우 사용자(User) 객체를 반환합니다.
    
    💡 [2중 정합성 및 자가 치유(Self-Healing)]:
    1. DB에서 UserSession과 User, UserProfile을 단 1회의 고속 JOIN(joinedload)으로 일괄 로드합니다.
    2. Redis에 세션 키가 살아있는지 검사합니다.
       - Redis에 존재: 정상 작동 (TTL 3일 슬라이딩 연장)
       - Redis에 부재(재부팅 등으로 휘발): DB 상태가 'ACTIVE'이므로 DB를 파괴하지 않고,
         오히려 Redis에 세션 키를 다시 복원(자가 치유)하여 유저 로그아웃을 방어합니다.
    3. Redis 일시 순단/에러(RedisError) 발생 시에도 시스템이 500으로 중단되지 않고
       안전하게 DB 세션으로 폴백합니다.
    """
    if not session_id:
        return None

    # 🚀 [개선 1] joinedload로 UserSession + User + UserProfile을 단 1번의 쿼리로 초고속 로드 (N+1 제거)
    db_session = (
        db.query(UserSession)
        .options(
            joinedload(UserSession.user).joinedload(User.profile)
        )
        .filter(
            UserSession.session_key == session_id,
            UserSession.status == "ACTIVE"
        )
        .first()
    )

    if not db_session or not db_session.user:
        return None

    user = db_session.user
    redis_key = f"session:{user.id}:{db_session.device_category}"

    # 🛡️ [개선 2] Redis 실시간 검증, 자가 치유(Self-Healing) 및 에러 방어막
    try:
        if not rd.sismember(redis_key, session_id):
            # ✨ [자가 치유 Self-Healing]:
            # Redis가 재부팅되어 메모리가 비워졌거나 TTL이 일찍 끝났더라도,
            # DB가 ACTIVE 상태라면 세션을 죽이지 않고 Redis에 키를 다시 복구 등록합니다!
            rd.sadd(redis_key, session_id)
            rd.expire(redis_key, SESSION_EXPIRE_SECONDS)
            logger.info(
                f"✨ [Session Self-Healing] Redis 세션 복구 완료 "
                f"(User: {user.username}, Device: {db_session.device_category})"
            )
        else:
            # 정상 활동: 슬라이딩 윈도우 TTL 3일 연장
            rd.expire(redis_key, SESSION_EXPIRE_SECONDS)
    except RedisError as redis_err:
        # 🛡️ [장애 방어]: Redis 일시 순단 시 500 에러를 뿜지 않고 DB 세션으로 안전 통과
        logger.warning(f"⚠️ [Session] Redis 일시 통신 장애, DB 세션으로 안전 폴백: {redis_err}")

    # [3단계] DB 최근 활동 시각(last_activity) 스로틀링 갱신 (5분 주기 DB Commit 락 경합 방지)
    now = datetime.now()
    if (
        not db_session.last_activity
        or (now - db_session.last_activity).total_seconds() >= ACTIVITY_UPDATE_INTERVAL_SECONDS
    ):
        db_session.last_activity = now
        db.commit()

    return user


def terminate_session(db: Session, session_id: Optional[str]) -> bool:
    """
    로그아웃 시 세션을 종료합니다.
    Redis에서 해당 JTI를 삭제하고, DB 상태를 'LOGOUT'으로 변경합니다.
    """
    if not session_id:
        return False

    db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
    if db_session:
        # Redis Set에서 세션 삭제
        redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
        rd.srem(redis_key, session_id)

        # DB 세션 상태 업데이트
        db_session.status = "LOGOUT"
        db_session.logout_at = datetime.now()
        db.commit()
        return True

    return False
