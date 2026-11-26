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
import json
import logging
import redis
from datetime import datetime, timedelta
from typing import Optional, Tuple, Iterable, Dict, Any
from fastapi import Request, Response
from sqlalchemy.orm import Session, joinedload, make_transient_to_detached
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
# Redis 캐시(session:cache:{jti})로 5분간 DB 무쿼리 고속 응답을 제공하고,
# 캐시 만료(5분 주기) 또는 Redis 장애 시에만 DB 조회 및 슬라이딩 갱신을 수행합니다.
ACTIVITY_UPDATE_INTERVAL_SECONDS = 300
SESSION_CACHE_PREFIX = "session:cache:"


def _session_cache_key(session_id: str) -> str:
    return f"{SESSION_CACHE_PREFIX}{session_id}"


def invalidate_session_cache(session_ids: Iterable[str]) -> None:
    """특정 세션 키(JTI)들의 Redis 유저 캐시를 즉시 무효화합니다."""
    keys = [_session_cache_key(str(s)) for s in session_ids if s]
    if not keys:
        return
    try:
        rd.delete(*keys)
    except RedisError:
        pass


def invalidate_user_session_caches(db: Session, user_id: Optional[int] = None) -> None:
    """사용자 권한(랭크·그룹·활성상태) 변경 시 해당 사원(또는 전체)의 활성 세션 캐시를 즉시 파기합니다."""
    try:
        q = db.query(UserSession.session_key).filter(UserSession.status == "ACTIVE")
        if user_id is not None:
            q = q.filter(UserSession.user_id == int(user_id))
        jtis = [row[0] for row in q.all() if row and row[0]]
        if jtis:
            invalidate_session_cache(jtis)
    except Exception:
        pass


def _save_session_cache(
    session_id: str,
    user: User,
    device_category: str,
    ttl_seconds: int = ACTIVITY_UPDATE_INTERVAL_SECONDS,
) -> None:
    """검증된 세션·유저·프로필 스냅샷을 Redis에 단기 캐싱하여 후속 API의 DB 쿼리를 0회로 줄입니다."""
    if not session_id or not user:
        return
    profile = getattr(user, "profile", None)
    payload = {
        "user_id": user.id,
        "username": user.username,
        "email": getattr(user, "email", "") or "",
        "real_name": getattr(user, "real_name", None),
        "phone": getattr(user, "phone", None),
        "has_profile": profile is not None,
        "rank_level": int(getattr(profile, "rank_level", 0) or 0) if profile else 0,
        "primary_group": getattr(profile, "primary_group", None) if profile else None,
        "secondary_groups": list(getattr(profile, "secondary_groups", None) or []) if profile else [],
        "is_active": bool(getattr(profile, "is_active", True)) if profile is not None else True,
        "device_category": device_category,
    }
    safe_ttl = max(15, min(int(ttl_seconds), ACTIVITY_UPDATE_INTERVAL_SECONDS))
    try:
        rd.setex(_session_cache_key(session_id), safe_ttl, json.dumps(payload, ensure_ascii=False))
    except RedisError:
        pass


def _load_session_cache(session_id: str) -> Optional[Dict[str, Any]]:
    """Redis에서 캐싱된 세션 스냅샷을 초고속 조회합니다. (미스 또는 장애 시 None 반환 -> DB 폴백)"""
    try:
        raw = rd.get(_session_cache_key(session_id))
        if not raw or not isinstance(raw, (str, bytes)):
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) and "user_id" in data else None
    except (RedisError, ValueError, TypeError):
        return None


def _hydrate_cached_user(db: Session, data: Dict[str, Any]) -> User:
    """
    캐시 스냅샷으로부터 SQLAlchemy 세션 호환 User + UserProfile 객체를 무쿼리(load=False) 복원합니다.
    - db.merge(..., load=False)를 통해 SQL 쿼리를 단 1회도 실행하지 않으면서도
      라우터에서 `Alert(user=current_user)` 등 ORM 관계 할당 시 정상 동작하도록 보장합니다.
    """
    from models import UserProfile

    user = User(
        id=int(data["user_id"]),
        username=data.get("username") or "",
        email=data.get("email") or "",
        password="",
        real_name=data.get("real_name"),
        phone=data.get("phone"),
    )
    profile = None
    if data.get("has_profile", True):
        profile = UserProfile(
            user_id=int(data["user_id"]),
            rank_level=int(data.get("rank_level", 0) or 0),
            primary_group=data.get("primary_group"),
            secondary_groups=list(data.get("secondary_groups") or []),
            is_active=bool(data.get("is_active", True)),
        )

    if isinstance(db, Session):
        make_transient_to_detached(user)
        user = db.merge(user, load=False)
        if profile is not None:
            make_transient_to_detached(profile)
            profile = db.merge(profile, load=False)
        user.__dict__["profile"] = profile
    else:
        user.profile = profile

    return user


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

    # 1순위: Cloudflare Tunnel이 검증하여 주입한 원본 클라이언트 IP (외부 XFF 스푸핑 원천 방어)
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()

    # 2순위: X-Real-IP (Nginx 리버스 프록시가 확정한 단일 클라이언트 IP)
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip and x_real_ip.strip():
        return x_real_ip.strip()

    # 3순위: X-Forwarded-For ("client, proxy1, proxy2" 중 가장 앞의 원본 클라이언트 IP)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip

    # 4순위: 직접 연결된 소켓 클라이언트 호스트
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def is_cookie_secure(request: Optional[Request] = None) -> bool:
    """
    session_id 쿠키에 Secure 플래그를 부여할지 자동 판별합니다.
    1. 환경변수 COOKIE_SECURE=True가 명시된 경우 무조건 True
    2. 프록시(Cloudflare Tunnel / Nginx)의 X-Forwarded-Proto가 https이거나 요청 스킴이 https인 경우 True
    3. 로컬 개발(http://localhost) 직통 접속 시에만 False
    """
    if settings.COOKIE_SECURE:
        return True
    if request is None:
        return False
    proto_header = request.headers.get("x-forwarded-proto", "")
    if proto_header:
        first_proto = proto_header.split(",")[0].strip().lower()
        if first_proto == "https":
            return True
    scheme = getattr(getattr(request, "url", None), "scheme", "") or ""
    return scheme.lower() == "https"


def set_session_cookie(
    response: Response,
    session_id: str,
    request: Optional[Request] = None,
    max_age: int = SESSION_EXPIRE_SECONDS,
) -> None:
    """로그인 및 슬라이딩 윈도우 공통 session_id 쿠키 발급 헬퍼."""
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=max_age,
        samesite="lax",
        secure=is_cookie_secure(request),
        path="/",
    )


def clear_session_cookie(response: Response, request: Optional[Request] = None) -> None:
    """로그아웃 시 발급 당시와 동일한 속성(secure/samesite/httponly/path)으로 쿠키를 확실히 제거합니다."""
    response.delete_cookie(
        key="session_id",
        path="/",
        secure=is_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )


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
    정상 로그인 성공 시 해당 계정+IP의 실패 카운터만 초기화합니다.
    (단일 IP 전역 카운터 ip_key는 유지하여, 공격자가 정상 계정 1개로 로그인해 IP 스캐닝 카운터를 리셋하는 우회를 차단합니다.)
    """
    user_key, _ = _get_login_fail_keys(username, ip_address)
    try:
        rd.delete(user_key)
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
    now = datetime.now()

    # [1단계] DB(진실 공급원) + Redis 양쪽에서 기존 동일 기기 ACTIVE 세션을 전수 조회하여 KICKED_OUT 처리
    # 💡 Redis 재부팅/휘발 직후 로그인하더라도 DB의 기존 ACTIVE 세션이 누락되어 자가치유로 부활하는 현상을 원천 차단합니다.
    db_active_sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user.id,
            UserSession.device_category == device_category,
            UserSession.status == "ACTIVE",
        )
        .all()
    )
    kicked_jtis = set()
    for old_sess in db_active_sessions:
        old_sess.status = "KICKED_OUT"
        old_sess.logout_at = now
        if old_sess.session_key:
            kicked_jtis.add(str(old_sess.session_key))

    try:
        existing_jtis = rd.smembers(redis_key)
        for jti_item in existing_jtis:
            old_jti = jti_item.decode("utf-8") if isinstance(jti_item, bytes) else str(jti_item)
            if old_jti not in kicked_jtis:
                updated = (
                    db.query(UserSession)
                    .filter(
                        UserSession.session_key == old_jti,
                        UserSession.status == "ACTIVE",
                    )
                    .update({"status": "KICKED_OUT", "logout_at": now})
                )
                if updated:
                    kicked_jtis.add(old_jti)
        rd.delete(redis_key)
    except RedisError as redis_err:
        logger.warning(f"⚠️ [Session Create] 기존 Redis 세션 정리 실패 (DB 기준으로 계속 진행): {redis_err}")

    for old_jti in kicked_jtis:
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
    if kicked_jtis:
        db.commit()
        invalidate_session_cache(kicked_jtis)
        try:
            from domain.ws.ws_service import manager
            manager.schedule_close_by_session_ids(kicked_jtis, code=1008)
        except Exception:
            pass

    # [2단계] 새로운 고유 세션 키(JTI) 발급 (Redis 장애 시에도 DB 세션으로 로그인 성공 보장)
    new_jti = str(uuid.uuid4())
    try:
        rd.sadd(redis_key, new_jti)
        rd.expire(redis_key, SESSION_EXPIRE_SECONDS)
    except RedisError as redis_err:
        logger.warning(f"⚠️ [Session Create] 신규 세션 Redis 적재 실패 (추후 자가치유로 복구됨): {redis_err}")

    # [3단계] DB에 새로운 세션 기록 저장
    db_session = UserSession(
        user_id=user.id,
        session_key=new_jti,
        device_category=device_category,
        status="ACTIVE",
        device_name=user_agent[:200], # 너무 긴 UA는 자름
        ip_address=ip_address,
        login_at=now,
        last_activity=now
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
    _save_session_cache(new_jti, user, device_category, ACTIVITY_UPDATE_INTERVAL_SECONDS)

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
        if isinstance(rd, redis.Redis):
            pipe = rd.pipeline(transaction=False)
            pipe.sismember(redis_key, session_id)
            pipe.expire(redis_key, SESSION_EXPIRE_SECONDS)
            is_member, _ = pipe.execute()
            if not is_member:
                heal_pipe = rd.pipeline(transaction=False)
                heal_pipe.sadd(redis_key, session_id)
                heal_pipe.expire(redis_key, SESSION_EXPIRE_SECONDS)
                heal_pipe.execute()
                actor = f"User: {username}" if username else f"UID={db_session.user_id}"
                logger.info(
                    f"✨ [{log_context}] Redis 세션 복구 완료 "
                    f"({actor}, Device: {db_session.device_category}, Session: {session_id[:8]}...)"
                )
        elif not rd.sismember(redis_key, session_id):
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

    # ⚡ [0단계: Redis-First 무쿼리 캐시 조회]
    # Redis가 정상이고 5분 내 검증된 캐시가 있으면 PostgreSQL 쿼리 없이 0.1ms 만에 즉시 반환합니다.
    # (단, 기기 불일치나 비활성 계정이 감지되면 캐시를 파기하고 아래 DB 정밀 검증·차단 경로로 넘깁니다.)
    cached = _load_session_cache(session_id)
    if cached is not None:
        if cached.get("is_active") is False:
            invalidate_session_cache([session_id])
        else:
            device_ok = True
            if request is not None:
                req_ua = request.headers.get("user-agent", "")
                if req_ua and (
                    "mozilla/" in req_ua.lower()
                    or "mobi" in req_ua.lower()
                    or "iphone" in req_ua.lower()
                    or "android" in req_ua.lower()
                ):
                    expected_dev = cached.get("device_category")
                    if expected_dev and detect_device_category(req_ua) != expected_dev:
                        device_ok = False
                        invalidate_session_cache([session_id])
            if device_ok:
                return _hydrate_cached_user(db, cached)

    # 🚀 [1단계: 캐시 미스 또는 Redis 기동 불가 시 DB 폴백 조회]
    # joinedload로 UserSession + User + UserProfile을 단 1번의 쿼리로 로드합니다.
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
        try:
            from domain.ws.ws_service import manager
            manager.schedule_close_by_session_ids([session_id], code=1008)
        except Exception:
            pass
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

    # [3단계] DB 최근 활동 시각(last_activity) 스로틀링 갱신 + 브라우저 쿠키 슬라이딩 갱신 마킹 + Redis 캐시 적재
    elapsed_sec = (
        (now - db_session.last_activity).total_seconds()
        if db_session.last_activity
        else ACTIVITY_UPDATE_INTERVAL_SECONDS
    )
    if not db_session.last_activity or elapsed_sec >= ACTIVITY_UPDATE_INTERVAL_SECONDS:
        db_session.last_activity = now
        db.commit()
        if request is not None:
            request.state.renew_session_id = session_id
        cache_ttl = ACTIVITY_UPDATE_INTERVAL_SECONDS
    else:
        cache_ttl = max(15, int(ACTIVITY_UPDATE_INTERVAL_SECONDS - elapsed_sec))

    _save_session_cache(session_id, user, db_session.device_category, cache_ttl)

    return user


def terminate_session(db: Session, session_id: Optional[str]) -> bool:
    """
    로그아웃 시 세션을 종료합니다.
    Redis에서 해당 JTI를 삭제하고, DB 상태를 'LOGOUT'으로 변경합니다.
    """
    if not session_id:
        return False

    invalidate_session_cache([session_id])
    db_session = db.query(UserSession).filter(UserSession.session_key == session_id).first()
    if db_session:
        # Redis Set에서 세션 삭제 (Redis 순단 시에도 DB 로그아웃은 정상 완료)
        redis_key = f"session:{db_session.user_id}:{db_session.device_category}"
        try:
            rd.srem(redis_key, session_id)
        except RedisError as redis_err:
            logger.warning(f"⚠️ [Session Logout] Redis 세션 키 제거 실패 (DB 로그아웃은 완료): {redis_err}")

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
        try:
            from domain.ws.ws_service import manager
            manager.schedule_close_by_session_ids([session_id], code=1008)
        except Exception:
            pass
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
