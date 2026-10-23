"""
============================================================================
[백엔드 공통 의존성 주입 사령탑 (core/deps.py)]
============================================================================

💡 이 파일의 역할:
FastAPI의 `Depends(...)`에서 사용되는 시스템 전역 핵심 의존성(Dependencies)을 제공합니다.

🌟 장점:
1. 기존에는 `from domain.user.user_router import get_current_user` 처럼
   비즈니스 라우터를 직접 참조하던 기형적 결합을 완전히 끊어냈습니다.
2. 어떤 신규 앱(배차, 게시판, 신규 플러그인 등)이든 `from core.deps import get_current_user`
   한 줄로 로그인된 사용자를 손쉽게 주입받을 수 있습니다.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Cookie, Request
from starlette import status
from sqlalchemy.orm import Session
from database import get_db
from models import User
from core.session import validate_session


def get_current_user(
    request: Request,
    session_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> User:
    """
    [필수 인증 의존성]
    로그인한 사용자만 접근 가능한 API에 사용합니다.
    - 세션 쿠키가 없거나 유효하지 않으면 401 Unauthorized 예외를 발생시킵니다.
    - 세션이 정상이면 슬라이딩 윈도우(만료 연장)를 적용하고 User 객체를 반환합니다.
    """
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다."
        )

    user = validate_session(db, session_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었거나 다른 기기에서 로그인하여 접속이 종료되었습니다."
        )

    return user


def get_current_user_optional(
    request: Request,
    session_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    [선택적 인증 의존성]
    로그인하지 않은 손님(Guest)도 접근 가능하지만,
    로그인한 유저가 오면 유저 정보를 알고 싶을 때(예: 게시글 목록 조회) 사용합니다.
    - 비로그인이거나 세션 오류 시 예외 대신 None 을 반환합니다.
    """
    if not session_id:
        return None

    try:
        return validate_session(db, session_id)
    except Exception:
        return None


class RankChecker:
    """
    [권한 등급 검사기 (클래스형)]
    특정 등급(0: Guest, 1: 준회원, 2: 정회원, 3: 매니저, 4: 최고관리자) 이상만
    허용하도록 라우터에서 `Depends(RankChecker(required_rank=2))` 형태로 사용합니다.
    """
    def __init__(self, required_rank: int):
        self.required_rank = required_rank

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
        if user_rank < self.required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 부족합니다. (필요 등급: {self.required_rank})"
            )
        return current_user


def check_rank(required_rank: int):
    """
    [권한 등급 검사기 (함수형 팩토리)]
    `Depends(check_rank(2))` 형태로 간편하게 권한을 검사합니다.
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        user_rank = current_user.rank() if callable(current_user.rank) else current_user.rank
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 부족합니다. (필요 등급: {required_rank})"
            )
        return current_user
    return _check
