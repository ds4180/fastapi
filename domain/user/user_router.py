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
)

# 📌 외부 라우터들의 하위 호환성을 위해 Re-export 등록
__all__ = [
    "router",
    "get_current_user",
    "get_current_user_optional",
    "RankChecker",
    "check_rank",
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
    """현재 로그인된 사용자의 기본 정보 및 권한 등급(rank_level) 반환"""
    rank_val = current_user.rank() if callable(current_user.rank) else current_user.rank
    return user_schema.User(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        rank_level=rank_val
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
    current_user: User = Depends(get_current_user)
):
    """최근 접속한 사용자 세션 목록 조회"""
    return user_crud.get_session_list(db)


# ----------------------------------------------------------------------------
# 5. 특정 세션 강제 추방 엔드포인트 (/users/sessions/kick/{target_session_id})
# ----------------------------------------------------------------------------
@router.post("/sessions/kick/{target_session_id}")
def kick_user_session(
    target_session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """관리자 전용: 특정 사용자의 세션을 강제로 만료(추방)시킵니다."""
    user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
    if user_rank < 4:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="권한 부족")

    result = user_crud.kick_session(db, session_id=target_session_id)
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
