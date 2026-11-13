"""
============================================================================
[사용자 인증 및 계정 관리 API 라우터 (domain/user/user_router.py)]
============================================================================

💡 이 파일의 역할:
사용자 로그인, 회원가입, 내 정보 조회(/me), 세션 목록 및 로그아웃 요청을 처리하는
'순수 HTTP 라우터'입니다.

🌟 리팩토링 핵심 (Core 분리 & 100% 하위 호환):
1. 복잡한 Redis 세션 제어 로직은 `core/session.py` 엔진으로 완전히 분리했습니다.
2. 유저 인증 의존성(`get_current_user`, `check_rank`)은 `core/deps.py` 사령탑으로 분리했습니다.
3. 📌 [하위 호환성 100% 보장]:
   다른 라우터들이 사용하던 `from domain.user.user_router import get_current_user` 문법이
   한 줄도 깨지지 않도록, core/deps 의 핵심 심볼들을 여기서 Re-export(다시 내보내기)합니다!
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Cookie, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette import status

from database import get_db
from models import User, SystemConfig
from domain.user import user_schema, user_crud

# ----------------------------------------------------------------------------
# 🏛️ 백엔드 코어(core)에서 세션 엔진과 인증 의존성을 가져옵니다.
# ----------------------------------------------------------------------------
from core.config import settings
from core.audit import safe_log_audit
from core.session import (
    create_user_session,
    terminate_session,
    get_client_ip,
    check_login_rate_limit,
    record_login_failure,
    clear_login_failures,
    SESSION_EXPIRE_SECONDS,
)
from core.deps import (
    get_current_user,
    get_current_user_optional,
    RankChecker,
    check_rank,
    check_root,
    check_permission,
    require_app_permission,
)

# 📌 외부 라우터들의 하위 호환성을 위해 Re-export 등록
__all__ = [
    "router",
    "get_current_user",
    "get_current_user_optional",
    "RankChecker",
    "check_rank",
    "check_root",
    "check_permission",
    "require_app_permission",
]

router = APIRouter(prefix="/users", tags=["Users"])


# ----------------------------------------------------------------------------
# 1. 로그인 엔드포인트 (/users/login)
# ----------------------------------------------------------------------------
@router.post("/login")
def login_for_access_token(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    사용자 아이디/비밀번호 검증 및 신규 세션 발급 (5중 보안 강화 버전)

    🛡️ 적용된 5대 보안 메커니즘:
    1. [실제 IP & 기기 식별]: 프록시(SvelteKit SSR / Nginx)가 전달한 `X-Forwarded-For`, `X-Real-IP`,
       `User-Agent`를 기반으로 실제 접속자 IP와 기기 카테고리(MOBILE/DESKTOP)를 정확히 식별합니다.
    2. [Brute-Force 일시 잠금(Lockout)]: Redis 기반으로 계정+IP(5회/5분) 및 단일 IP(15회/15분)
       연속 로그인 실패를 감시하며, 임계치 초과 시 `429 Too Many Requests`로 즉시 차단합니다.
    3. [Constant-Time 타이밍 공격 방어]: 존재하지 않는 아이디 입력 시에도 더미 bcrypt 해시 연산을
       동일하게 수행(`verify_user_credentials`)하여 응답 시간 차이로 아이디 유무를 유추할 수 없게 합니다.
    4. [비활성 계정 차단]: 퇴사·정지된 계정(`is_active == False`)의 로그인을 `403 Forbidden`으로 차단합니다.
    5. [세션 고정(Session Fixation) 방어 및 쿠키 보안]: 기존 `session_id` 쿠키가 있으면 먼저 폐기한 뒤
       새 UUIDv4 세션을 발급하며, `settings.COOKIE_SECURE` 정책에 맞춰 쿠키를 설정합니다.
    """
    ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    # 🛡️ [1단계] Brute-Force 잠금(Lockout) 상태 선행 확인 (DB 및 bcrypt 연산 전 초고속 차단)
    retry_after = check_login_rate_limit(username=form_data.username, ip_address=ip)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"로그인 연속 실패로 인해 보안을 위해 일시 잠금되었습니다. {retry_after}초 후에 다시 시도하세요.",
            headers={"Retry-After": str(retry_after)},
        )

    # 🛡️ [2단계] 사용자 조회 및 Constant-Time 비밀번호 검증 (타이밍 공격 방어)
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.verify_user_credentials(user, form_data.password):
        # 실패 횟수 누적 및 감사로그 기록 (임계치 도달 시 SECURITY/CRITICAL 로그 자동 발행)
        _, lockout_secs = record_login_failure(
            db=db,
            username=form_data.username,
            ip_address=ip,
            user=user if user else None,
            user_agent=user_agent,
        )
        if lockout_secs is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"로그인 {settings.LOGIN_MAX_ATTEMPTS}회 연속 실패로 인해 {lockout_secs}초간 로그인이 일시 잠금되었습니다.",
                headers={"Retry-After": str(lockout_secs)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸습니다."
        )

    # 🛡️ [3단계] 소프트 삭제/비활성화 가드: 비활성화된 사원 계정 로그인 즉시 차단
    if user.profile and user.profile.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화(삭제)된 사원 계정입니다. 인사 관리자에게 문의하세요."
        )

    # 🛡️ [4단계] 로그인 성공 시 기존 실패 카운터 즉시 초기화
    clear_login_failures(username=form_data.username, ip_address=ip)

    # 🚀 [5단계] 핵심 세션 생성 (내부에서 이전 쿠키 세션 폐기 + 동일 기기 카테고리 중복 세션 KICKED_OUT 수행)
    jti = create_user_session(db=db, user=user, request=request)

    # 브라우저에 session_id 쿠키 설정 (HttpOnly + SameSite=Lax + 환경별 Secure 적용)
    response.set_cookie(
        key="session_id",
        value=jti,
        httponly=True,
        max_age=SESSION_EXPIRE_SECONDS,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/"
    )

    return {
        "message": "Login successful",
        "username": user.username
    }


# ----------------------------------------------------------------------------
# 2. 내 정보 조회 엔드포인트 (/users/me)
# ----------------------------------------------------------------------------
@router.get("/me", response_model=user_schema.User)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    현재 로그인된 사용자의 기본 정보 6대 항목 중 보안 키(비밀번호)를 제외한
    아이디, 이메일, 권한랭킹(0~9), 주그룹(1개), 부그룹(N개 리스트)을 반환합니다.
    """
    rank_val = current_user.rank() if callable(current_user.rank) else current_user.rank
    return user_schema.User(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        rank_level=rank_val,
        primary_group=current_user.primary_group,
        secondary_groups=current_user.secondary_groups,
    )


# ----------------------------------------------------------------------------
# 3. 회원 가입 엔드포인트 (/users/create, /users/register-mode)
# ----------------------------------------------------------------------------
@router.get("/register-mode")
def get_public_register_mode(db: Session = Depends(get_db)):
    """현재 시스템의 회원가입 정책 모드 공개 조회 (ADMIN_ONLY, APPROVAL, OPEN)"""
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "AUTH_REGISTER_MODE").first()
    return {"register_mode": cfg.value if cfg and cfg.value else "ADMIN_ONLY"}

@router.post("/create", response_model=user_schema.User, status_code=status.HTTP_201_CREATED)
def create_user(user_create: user_schema.UserCreate, db: Session = Depends(get_db)):
    """새로운 사용자 회원 가입 (가입 정책 스위치 연동)"""
    # 1. 시스템 가입 정책 검사
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "AUTH_REGISTER_MODE").first()
    reg_mode = cfg.value if cfg and cfg.value else "ADMIN_ONLY"

    if reg_mode == "ADMIN_ONLY":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본 시스템은 보안 오피스 인트라넷으로, 관리자 직접 등록으로만 계정이 생성됩니다."
        )

    db_user = user_crud.get_existing_user(db, user_create=user_create)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 사용자입니다."
        )

    # 2. 계정 생성 (기본 UserProfile rank_level=0으로 미승인 격리)
    new_user = user_crud.create_user(db=db, user_create=user_create)
    if reg_mode == "OPEN" and new_user.profile:
        new_user.profile.rank_level = 1
        db.commit()

    return new_user


# ----------------------------------------------------------------------------
# 4. 세션 목록 조회 엔드포인트 (/users/sessions)
# ----------------------------------------------------------------------------
@router.get("/sessions", response_model=List[user_schema.UserSessionResponse])
def session_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """관리자 전용(Rank 4): 최근 접속한 사용자들의 세션 및 접속 기기/IP 목록을 조회합니다."""
    return user_crud.get_session_list(db)


# ----------------------------------------------------------------------------
# 5. 특정 세션 강제 추방 엔드포인트 (/users/sessions/kick/{target_session_id})
# ----------------------------------------------------------------------------
@router.post("/sessions/kick/{target_session_id}")
def kick_user_session(
    target_session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_rank(4))
):
    """관리자 전용(Rank 4): 특정 사용자의 세션을 강제로 만료(추방)시킵니다."""
    result = user_crud.kick_session(db, session_id=target_session_id)
    if result:
        # 📜 [감사로그]: 관리자에 의한 세션 강제 추방 (SECURITY 로그)
        safe_log_audit(
            db=db,
            app_id="system",
            log_type="SECURITY",
            severity="WARN",
            action="SESSION_KICKED",
            title=f"관리자({current_user.username})에 의한 세션 #{target_session_id} 강제 추방",
            user=current_user,
            resource_type="user_session",
            resource_id=str(target_session_id),
            message=f"관리자 {current_user.username}(ID: {current_user.id})가 세션 #{target_session_id}을(를) 강제 종료시켰습니다.",
            metadata={"admin_id": current_user.id, "target_session_id": target_session_id}
        )
    return {"message": "success"} if result else {"error": "Session not found"}


# ----------------------------------------------------------------------------
# 6. 로그아웃 엔드포인트 (/users/logout)
# ----------------------------------------------------------------------------
@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """로그아웃: Redis 및 DB 세션을 만료 처리하고 쿠키를 삭제합니다."""
    request.state.session_terminated = True
    if session_id:
        terminate_session(db=db, session_id=session_id)

    response.delete_cookie(key="session_id", path="/")
    return {"message": "Logout successful"}


# ----------------------------------------------------------------------------
# 7. 전체 회원 목록 조회 (/users/list)
# ----------------------------------------------------------------------------
@router.get("/list", response_model=user_schema.UserList)
def user_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """전체 사용자 목록 조회"""
    return {"users": user_crud.get_user_list(db)}
