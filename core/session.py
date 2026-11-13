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
from datetime import datetime, timedelta
from typing import Optional, Tuple
from fastapi import Request
from sqlalchemy.orm import Session, joinedload
from redis.exceptions import RedisError
from redis_config import rd
from models import User, UserSession
from core.config import settings
from core.audit import safe_log_audit

logger = logging.getLogger("core.session")

# 📌 세션 유효 기간 (일 단위) - 중앙 설정소에서 가져옴
SESSION_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
SESSION_EXPIRE_SECONDS = 60 * 60 * 24 * SESSION_EXPIRE_DAYS

# 📌 DB 최근 활동 시각(last_activity) 갱신 최소 주기 (5분 = 300초)
# 매 API 요청마다 DB COMMIT을 수행하면 동시 요청 시 Row Lock 경합이 발생하므로,
# Redis 만료 시간은 매번 즉시 연장하되 DB 기록은 5분 주기로 스로틀링(Throttling)합니다.
ACTIVITY_UPDATE_INTERVAL_SECONDS = 300


# ============================================================================
# 🌐 [보안 강화 1] 프록시(SvelteKit SSR / Nginx) 투과 실제 클라이언트 IP 추출기
# ============================================================================
def get_client_ip(request: Optional[Request]) -> str:
    """
    리버스 프록시(Nginx) 또는 프론트엔드 SSR 서버(SvelteKit Form Action / Hooks)를
    경유하여 들어오는 요청에서 실제 사용자 단말의 공인/사설 IP 주소를 추출합니다.

    💡 왜 필요한가?
    - SvelteKit SSR 서버가 백엔드로 로그인 요청을 대신 전달할 때 `request.client.host`만 읽으면
      모든 사용자의 접속 IP가 도커 컨테이너 내부 IP(예: 172.18.0.x)로 동일하게 기록됩니다.
    - 이를 해결하기 위해 프록시 표준 헤더인 `X-Forwarded-For`(최초 홉 IP) 및 `X-Real-IP`를
      우선 파싱하고, 없을 때만 `request.client.host`로 폴백합니다.
    """
    if request is None:
        return "unknown"

    # 1순위: X-Forwarded-For ("client, proxy1, proxy2" 중 가장 앞의 원본 클라이언트 IP)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip

    # 2순위: X-Real-IP (Nginx 등에서 단일 클라이언트로 지정한 헤더)
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip and x_real_ip.strip():
        return x_real_ip.strip()

    # 3순위: 직접 연결된 소켓 클라이언트 호스트
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


# ============================================================================
# 🛡️ [보안 강화 2] Redis 기반 무차별 대입(Brute-Force) 방어 및 일시 잠금 엔진
# ============================================================================
def _get_login_fail_keys(username: str, ip_address: str) -> Tuple[str, str]:
    """
    로그인 실패 카운팅을 위한 Redis Key 쌍을 생성합니다.
    1. user_key: 특정 계정(username)에 대한 특정 IP의 연속 실패 횟수 (계정 표적 공격 방어)
    2. ip_key: 단일 IP에서 여러 계정을 돌아가며 찌르는(Credential Stuffing) 전체 실패 횟수
    """
    normalized_user = (username or "anonymous").strip().lower()
    normalized_ip = (ip_address or "unknown").strip()
    user_key = f"login_fail:user:{normalized_user}:{normalized_ip}"
    ip_key = f"login_fail:ip:{normalized_ip}"
    return user_key, ip_key


def check_login_rate_limit(username: str, ip_address: str) -> Optional[int]:
    """
    로그인 시도 전 해당 계정+IP 또는 단일 IP가 잠금(Lockout) 상태인지 확인합니다.

    - 잠금 상태인 경우: 남은 잠금 해제 대기 시간(초, int > 0)을 반환합니다.
    - 정상 상태인 경우: None을 반환합니다.
    - 🛡️ [Fail-Safe]: Redis 일시 장애 시에는 로그인 자체가 마비되지 않도록 경고를 남기고 통과시킵니다.
    """
    user_key, ip_key = _get_login_fail_keys(username, ip_address)
    try:
        # 1. 단일 IP 전역 차단 임계치(기본 15회) 검사
        ip_fails_raw = rd.get(ip_key)
        if ip_fails_raw and int(ip_fails_raw) >= settings.LOGIN_IP_MAX_ATTEMPTS:
            ttl = rd.ttl(ip_key)
            return ttl if ttl and ttl > 0 else settings.LOGIN_IP_LOCKOUT_SECONDS

        # 2. 특정 계정+IP 차단 임계치(기본 5회) 검사
        user_fails_raw = rd.get(user_key)
        if user_fails_raw and int(user_fails_raw) >= settings.LOGIN_MAX_ATTEMPTS:
            ttl = rd.ttl(user_key)
            return ttl if ttl and ttl > 0 else settings.LOGIN_LOCKOUT_SECONDS
    except RedisError as redis_err:
        logger.warning(f"⚠️ [Login RateLimit] Redis 조회 실패, 잠금 검사 안전 우회: {redis_err}")

    return None


def record_login_failure(
    db: Session,
    username: str,
    ip_address: str,
    user: Optional[User] = None,
    user_agent: str = "",
) -> Tuple[int, Optional[int]]:
    """
    로그인 실패 시 Redis 실패 카운터를 1 증가시키고 감사로그(AuditLog)를 기록합니다.

    💡 핵심 보안 설계 (DB DoS 방어 + Watchdog 자동 연동):
    - 무차별 대입 공격 시 초당 수백 건의 DB INSERT가 발생하는 것을 방지하기 위해,
      임계치 도달 전 일반 실패는 `ACCESS / WARN (LOGIN_FAILED)`로 기록하고,
      임계치에 도달한 최초 순간에는 `SECURITY / CRITICAL (LOGIN_LOCKOUT)` 감사로그를 발행하여
      Watchdog 자율신경계가 관리자에게 즉시 보안 경보를 발송하도록 연동합니다.
    - 반환값: `(현재 계정 실패 횟수, 잠금 발동 시 대기 초 또는 None)`
    """
    user_key, ip_key = _get_login_fail_keys(username, ip_address)
    user_attempts = 1
    ip_attempts = 1
    lockout_seconds: Optional[int] = None

    try:
        # 1. 계정+IP 실패 카운터 증가 및 만료시간(기본 5분) 설정
        user_attempts = int(rd.incr(user_key))
        if user_attempts == 1:
            rd.expire(user_key, settings.LOGIN_LOCKOUT_SECONDS)

        # 2. 단일 IP 실패 카운터 증가 및 만료시간(기본 15분) 설정
        ip_attempts = int(rd.incr(ip_key))
        if ip_attempts == 1:
            rd.expire(ip_key, settings.LOGIN_IP_LOCKOUT_SECONDS)

        if ip_attempts >= settings.LOGIN_IP_MAX_ATTEMPTS:
            ttl = rd.ttl(ip_key)
            lockout_seconds = ttl if ttl and ttl > 0 else settings.LOGIN_IP_LOCKOUT_SECONDS
        elif user_attempts >= settings.LOGIN_MAX_ATTEMPTS:
            ttl = rd.ttl(user_key)
            lockout_seconds = ttl if ttl and ttl > 0 else settings.LOGIN_LOCKOUT_SECONDS
    except RedisError as redis_err:
        logger.warning(f"⚠️ [Login RateLimit] Redis 실패 카운터 기록 오류: {redis_err}")

    # 3. 감사로그 기록 (잠금 임계치 도달 순간에는 SECURITY 등급으로 격상하여 Watchdog 트리거)
    if user_attempts == settings.LOGIN_MAX_ATTEMPTS or ip_attempts == settings.LOGIN_IP_MAX_ATTEMPTS:
        safe_log_audit(
            db=db,
            app_id="auth",
            log_type="SECURITY",
            severity="CRITICAL",
            action="LOGIN_LOCKOUT",
            title=f"무차별 로그인 시도 차단 (계정: {username}, IP: {ip_address})",
            user=user,
            message=(
                f"연속 로그인 실패 임계치 도달(계정 {user_attempts}회 / IP {ip_attempts}회)로 "
                f"{lockout_seconds or settings.LOGIN_LOCKOUT_SECONDS}초간 로그인이 일시 차단되었습니다."
            ),
            ip_address=ip_address,
            metadata={
                "attempted_username": username,
                "user_attempts": user_attempts,
                "ip_attempts": ip_attempts,
                "lockout_seconds": lockout_seconds or settings.LOGIN_LOCKOUT_SECONDS,
                "user_agent": (user_agent or "")[:200],
            },
        )
    elif user_attempts < settings.LOGIN_MAX_ATTEMPTS:
        safe_log_audit(
            db=db,
            app_id="auth",
            log_type="ACCESS",
            severity="WARN",
            action="LOGIN_FAILED",
            title=f"로그인 실패 ({user_attempts}/{settings.LOGIN_MAX_ATTEMPTS}): {username}",
            user=user,
            message="비밀번호가 일치하지 않거나 존재하지 않는 계정입니다.",
            ip_address=ip_address,
            metadata={
                "attempted_username": username,
                "attempt_count": user_attempts,
                "max_attempts": settings.LOGIN_MAX_ATTEMPTS,
                "user_agent": (user_agent or "")[:200],
            },
        )

    return user_attempts, lockout_seconds


def clear_login_failures(username: str, ip_address: str) -> None:
    """
    정상 로그인 성공 시 해당 계정+IP 및 단일 IP의 실패 카운터를 즉시 초기화합니다.
    """
    user_key, ip_key = _get_login_fail_keys(username, ip_address)
    try:
        rd.delete(user_key, ip_key)
    except RedisError as redis_err:
        logger.warning(f"⚠️ [Login RateLimit] Redis 실패 카운터 초기화 오류: {redis_err}")


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
    
    1. [세션 고정(Session Fixation) 방어]: 요청 쿠키에 이전 `session_id`가 남아있다면
       먼저 안전하게 폐기(terminate_session)하여 기존 세션 키 재사용을 원천 차단합니다.
    2. 동일한 기기 카테고리(예: 모바일)에서 이미 로그인되어 있던 기존 세션을
       모두 'KICKED_OUT(강제 로그아웃)' 처리하고 Redis에서 삭제합니다.
    3. 새로운 세션 고유 키(UUID)를 생성하여 Redis와 DB에 등록합니다.
    4. 생성된 세션 키(str)를 반환합니다.
    """
    user_agent = request.headers.get("user-agent", "") if request else ""
    ip_address = get_client_ip(request)
    device_category = detect_device_category(user_agent)

    # 🛡️ [보안 강화 5 - Session Fixation 방어]:
    # 브라우저가 이전(또는 외부 주입된) session_id 쿠키를 들고 재로그인을 요청한 경우,
    # 해당 세션을 즉시 종료 처리하고 완전히 새로운 UUIDv4 JTI를 발급합니다.
    prior_session_id = request.cookies.get("session_id") if request and hasattr(request, "cookies") else None
    if prior_session_id:
        try:
            terminate_session(db=db, session_id=prior_session_id)
        except Exception as term_err:
            logger.warning(f"⚠️ [Session Fixation Guard] 기존 세션 정리 중 무시 가능한 오류: {term_err}")

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
        # 📜 [감사로그]: 중복 로그인으로 인한 이전 세션 강제 추방 자동 기록
        safe_log_audit(
            db=db,
            app_id="auth",
            log_type="ACCESS",
            severity="WARN",
            action="KICKED_OUT",
            title=f"중복 로그인으로 이전 {device_category} 세션 강제 종료 (KICKED_OUT)",
            user=user,
            ip_address=ip_address,
            metadata={"device": device_category, "session_key": old_jti[:8] + "..."},
            commit=False
        )
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

    # 📜 [감사로그]: 신규 로그인 세션 발급 완료 기록
    safe_log_audit(
        db=db,
        app_id="auth",
        log_type="ACCESS",
        severity="INFO",
        action="LOGIN_SUCCESS",
        title=f"{user.username} 로그인 성공 ({device_category})",
        user=user,
        ip_address=ip_address,
        metadata={"device": device_category, "user_agent": user_agent[:200]},
        commit=False
    )
    db.commit()

    return new_jti


def _is_session_inactive_expired(db_session: UserSession, now: datetime) -> bool:
    """최근 활동 시각(없으면 로그인 시각) 기준 비활동 만료(SESSION_EXPIRE_DAYS) 초과 여부 판별."""
    ref_time = db_session.last_activity or db_session.login_at
    return bool(ref_time and (now - ref_time) > timedelta(days=SESSION_EXPIRE_DAYS))


def _ensure_redis_session(
    db_session: UserSession,
    session_id: str,
    username: Optional[str] = None,
    log_context: str = "Session Self-Healing",
) -> None:
    """Redis Set 생존 확인, 휘발 시 자가치유 복구 및 슬라이딩 TTL(SESSION_EXPIRE_SECONDS) 연장."""
    redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
    try:
        if not rd.sismember(redis_key, session_id):
            # ✨ [자가 치유 Self-Healing]:
            # Redis가 재부팅되어 메모리가 비워졌거나 TTL이 일찍 끝났더라도,
            # DB가 ACTIVE 상태라면 세션을 죽이지 않고 Redis에 키를 다시 복구 등록합니다!
            rd.sadd(redis_key, session_id)
            rd.expire(redis_key, SESSION_EXPIRE_SECONDS)
            actor = f"User: {username}" if username else f"UID={db_session.user_id}"
            logger.info(
                f"✨ [{log_context}] Redis 세션 복구 완료 "
                f"({actor}, Device: {db_session.device_category}, Session: {session_id[:8]}...)"
            )
        else:
            # 정상 활동: 슬라이딩 윈도우 TTL 3일 연장
            rd.expire(redis_key, SESSION_EXPIRE_SECONDS)
    except RedisError as redis_err:
        # 🛡️ [장애 방어]: Redis 일시 순단 시 500 에러를 뿜지 않고 DB 세션으로 안전 통과
        logger.warning(f"⚠️ [{log_context}] Redis 일시 통신 장애, DB 세션으로 안전 폴백: {redis_err}")


def validate_session(
    db: Session,
    session_id: Optional[str],
    request: Optional[Request] = None,
) -> Optional[User]:
    """
    세션 키의 유효성을 검증하고, 유효한 경우 사용자(User) 객체를 반환합니다.

    💡 [2중 정합성, 비활동 만료 및 슬라이딩 윈도우]:
    1. DB에서 UserSession과 User, UserProfile을 단 1회의 고속 JOIN(joinedload)으로 일괄 로드합니다.
    2. 최근 활동 시각(last_activity, 없으면 login_at)이 SESSION_EXPIRE_DAYS를 초과한 경우
       DB 상태를 'EXPIRED'로 전환하고 Redis 키를 제거한 뒤 None을 반환합니다.
    3. Redis에 세션 키가 살아있는지 검사하고 휘발 시 자가치유 복구 및 TTL 3일 슬라이딩 연장합니다.
    4. 5분 스로틀링 주기에 도달하면 DB last_activity를 갱신하고 request.state.renew_session_id를
       표기하여 HTTP 응답 시 브라우저 session_id 쿠키의 Max-Age도 함께 슬라이딩 연장합니다.
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
    now = datetime.now()

    # 🛡️ [보안 강화 3 - 비활성화/퇴사 계정(is_active=False) 실시간 차단 가드]:
    # 로그인 당시에는 정상 계정이었으나, 이후 인사 관리자에 의해 비활성화(퇴사/정지) 처리된 경우
    # 기존에 발급된 3일짜리 세션 쿠키로 API를 계속 호출할 수 없도록 즉시 KICKED_OUT 처리합니다.
    if getattr(user, "profile", None) is not None and getattr(user.profile, "is_active", True) is False:
        db_session.status = "KICKED_OUT"
        db_session.logout_at = now
        try:
            rd.srem(f"session:{db_session.user_id}:{db_session.device_category}", session_id)
        except RedisError:
            pass
        db.commit()
        logger.warning(
            f"🚫 [Session Security] 비활성화된 계정(is_active=False)의 활성 세션 즉시 차단 "
            f"(User: {user.username}, Device: {db_session.device_category}, Session: {session_id[:8]}...)"
        )
        return None

    # 🛡️ [보안 강화 5 - 기기 카테고리 바인딩(Device Category Binding) 검증]:
    # PC(DESKTOP)에서 발급된 session_id 쿠키를 탈취하여 모바일(MOBILE) 브라우저에서 재사용하거나
    # 반대로 모바일 세션을 PC에서 재사용하는 세션 하이재킹(Session Hijacking)을 차단합니다.
    # (단, User-Agent가 없는 내부 테스트/배치 호출은 오탐 방지를 위해 스킵하고 실제 브라우저 UA만 검증)
    if request is not None:
        req_ua = request.headers.get("user-agent", "")
        if req_ua and ("mozilla/" in req_ua.lower() or "mobi" in req_ua.lower() or "iphone" in req_ua.lower() or "android" in req_ua.lower()):
            current_device = detect_device_category(req_ua)
            if db_session.device_category and current_device != db_session.device_category:
                db_session.status = "KICKED_OUT"
                db_session.logout_at = now
                try:
                    rd.srem(f"session:{db_session.user_id}:{db_session.device_category}", session_id)
                except RedisError:
                    pass
                safe_log_audit(
                    db=db,
                    app_id="auth",
                    log_type="SECURITY",
                    severity="WARN",
                    action="SESSION_DEVICE_MISMATCH",
                    title=f"세션 기기 불일치 감지 및 차단 ({db_session.device_category} -> {current_device})",
                    user=user,
                    ip_address=get_client_ip(request),
                    message="발급 당시 기기 카테고리와 다른 환경에서 세션 쿠키가 사용되어 세션을 즉시 폐기했습니다.",
                    metadata={
                        "expected_device": db_session.device_category,
                        "actual_device": current_device,
                        "session_key": session_id[:8] + "...",
                        "user_agent": req_ua[:200],
                    },
                    commit=False,
                )
                db.commit()
                return None

    # [2단계] DB 기준 비활동 만료(SESSION_EXPIRE_DAYS) 초과 시 즉시 만료 처리
    if _is_session_inactive_expired(db_session, now):
        db_session.status = "EXPIRED"
        db_session.logout_at = now
        try:
            rd.srem(f"session:{db_session.user_id}:{db_session.device_category}", session_id)
        except RedisError:
            pass
        db.commit()
        logger.info(
            f"⌛ [Session] 비활동 만료 처리 "
            f"(User: {user.username}, Device: {db_session.device_category}, Session: {session_id[:8]}...)"
        )
        return None

    # 🛡️ [개선 2] Redis 실시간 검증, 자가 치유(Self-Healing) 및 에러 방어막
    _ensure_redis_session(
        db_session,
        session_id,
        username=user.username,
        log_context="Session Self-Healing",
    )

    # [3단계] DB 최근 활동 시각(last_activity) 스로틀링 갱신 + 브라우저 쿠키 슬라이딩 갱신 마킹
    if (
        not db_session.last_activity
        or (now - db_session.last_activity).total_seconds() >= ACTIVITY_UPDATE_INTERVAL_SECONDS
    ):
        db_session.last_activity = now
        db.commit()
        if request is not None:
            request.state.renew_session_id = session_id

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

        # 📜 [감사로그]: 정상 로그아웃 기록
        user_obj = db.query(User).filter(User.id == db_session.user_id).first()
        safe_log_audit(
            db=db,
            app_id="auth",
            log_type="ACCESS",
            severity="INFO",
            action="LOGOUT",
            title=f"{user_obj.username if user_obj else f'UID {db_session.user_id}'} 로그아웃 ({db_session.device_category})",
            user=user_obj,
            ip_address=db_session.ip_address,
            metadata={"device": db_session.device_category, "session_key": session_id[:8] + "..."},
            commit=False
        )
        db.commit()
        return True

    return False


def sync_expired_sessions(db: Session) -> int:
    """
    [통합 세션 자가치유 및 비활동 만료 동기화 엔진 (SSOT)]

    1. DB를 단일 진실 공급원(SSOT)으로 삼아 비활동 만료 기간(SESSION_EXPIRE_DAYS)을
       초과한 세션만 EXPIRED 상태로 전환하고 Redis에서 제거합니다.
    2. 유효 기간 내인데 Redis에서 휘발된 ACTIVE 세션은 키를 자가치유(Self-Healing) 복원하여
       관리자 세션 목록 조회나 관제 동기화로 정상 세션이 끊어지는 사고를 방지합니다.
    """
    active_sessions = (
        db.query(UserSession)
        .filter(UserSession.status == "ACTIVE")
        .all()
    )
    valid_count = 0
    now = datetime.now()
    modified = False

    for s in active_sessions:
        if _is_session_inactive_expired(s, now):
            s.status = "EXPIRED"
            s.logout_at = now
            try:
                rd.srem(f"session:{s.user_id}:{s.device_category}", s.session_key)
            except RedisError:
                pass
            modified = True
            continue

        _ensure_redis_session(
            s,
            s.session_key,
            log_context="Session Sync",
        )
        valid_count += 1

    if modified:
        db.commit()

    return valid_count
