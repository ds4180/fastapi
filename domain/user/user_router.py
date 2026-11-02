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
from models import User
from domain.user import user_schema, user_crud

# ----------------------------------------------------------------------------
# 🏛️ 백엔드 코어(core)에서 세션 엔진과 인증 의존성을 가져옵니다.
# ----------------------------------------------------------------------------
from core.config import settings
from core.audit import safe_log_audit
from core.session import (
    create_user_session,
    terminate_session,
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
    사용자 아이디/비밀번호 검증 및 신규 세션 발급
    - 비밀번호 검증 성공 시 core.session 엔진을 통해 UUID 세션을 발급합니다.
    - 브라우저 쿠키(session_id)에 세션 키를 안전하게 설정합니다.
    """
    user = user_crud.get_user(db, username=form_data.username)
    if not user or not user_crud.pwd_context.verify(form_data.password, user.password):
        # 📜 [감사로그]: 로그인 실패 기록 (계정 존재 여부 및 비밀번호 불일치)
        ip = request.client.host if request.client else "unknown"
        safe_log_audit(
            db=db,
            app_id="auth",
            log_type="ACCESS",
            severity="WARN",
            action="LOGIN_FAILED",
            title=f"로그인 실패: {form_data.username}",
            user=user if user else None,
            message="비밀번호가 일치하지 않거나 존재하지 않는 계정입니다.",
            ip_address=ip,
            metadata={
                "attempted_username": form_data.username,
                "user_agent": request.headers.get("user-agent", "")[:200]
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 틀렸습니다."
        )

    # 🚀 핵심 세션 생성 로직을 core 엔진으로 단 한 줄로 위임!
    jti = create_user_session(db=db, user=user, request=request)

    # 브라우저에 session_id 쿠키 설정 (기존 설정 정책 100% 유지)
    response.set_cookie(
        key="session_id",
        value=jti,
        httponly=True,
        max_age=SESSION_EXPIRE_SECONDS,
        samesite="lax",
        secure=False
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
# 3. 회원 가입 엔드포인트 (/users/create)
# ----------------------------------------------------------------------------
@router.post("/create", response_model=user_schema.User, status_code=status.HTTP_201_CREATED)
def create_user(user_create: user_schema.UserCreate, db: Session = Depends(get_db)):
    """새로운 사용자 회원 가입"""
    db_user = user_crud.get_existing_user(db, user_create=user_create)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 사용자입니다."
        )
    return user_crud.create_user(db=db, user_create=user_create)


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
    response: Response,
    session_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """로그아웃: Redis 및 DB 세션을 만료 처리하고 쿠키를 삭제합니다."""
    if session_id:
        terminate_session(db=db, session_id=session_id)

    response.delete_cookie(key="session_id")
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
