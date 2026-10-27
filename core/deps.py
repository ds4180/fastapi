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

from typing import Optional, Iterable
from fastapi import Depends, HTTPException, Cookie, Request
from starlette import status
from sqlalchemy.orm import Session
from database import get_db
from models import User
from core.session import validate_session
from core.permission import (
    ROOT_RANK,
    get_user_rank,
    compare_rank,
    evaluate_permission,
)


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
    특정 랭킹(0~9) 조건을 만족하는 사용자만 허용하도록
    라우터에서 `Depends(RankChecker(required_rank=2))` 형태로 사용합니다.
    - root(랭킹 9)는 항상 통과합니다.
    - op 인자를 통해 '>=', '>', '==', '<=', '<' 비교 연산을 모두 지원합니다.
    """
    def __init__(self, required_rank: int, op: str = ">="):
        self.required_rank = required_rank
        self.op = op

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_rank = get_user_rank(current_user)
        if user_rank != ROOT_RANK and not compare_rank(user_rank, self.required_rank, self.op):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 부족합니다. (필요 랭킹 조건: {self.op} {self.required_rank})"
            )
        return current_user


def check_rank(required_rank: int, op: str = ">="):
    """
    [권한 등급 검사기 (함수형 팩토리)]
    `Depends(check_rank(2))` 또는 `Depends(check_rank(9, "=="))` 형태로 간편하게 랭킹을 검사합니다.
    - root(랭킹 9)는 항상 통과합니다.
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        user_rank = get_user_rank(current_user)
        if user_rank != ROOT_RANK and not compare_rank(user_rank, required_rank, op):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 부족합니다. (필요 랭킹 조건: {op} {required_rank})"
            )
        return current_user
    return _check


# 📌 [root(랭킹 9) 전용 가드]
# 주그룹/부그룹 생성·삭제·설정 등 오직 시스템 최고 절대 권한(root)만 수행 가능한 라우터에 사용합니다.
check_root = check_rank(ROOT_RANK, op="==")


def check_permission(
    action: str = "read",
    min_read_rank: int = 0,
    min_write_rank: int = 2,
    allow_groups: Optional[Iterable[str]] = None,
    deny_groups: Optional[Iterable[str]] = None,
    op: str = ">=",
):
    """
    [`정책재정의.md` 4단계 통합 권한 검사 의존성]
    신규 도메인 앱 라우터에서 그룹(deny/allow)과 랭킹(0~9)을 결합하여 검증할 때 사용합니다.
    
    처리 순서 (core.permission.evaluate_permission 위임):
    1. root(9) 인가? ➔ 통과
    2. deny_groups에 부그룹/주그룹이 있는가? ➔ 403 차단
    3. allow_groups에 부그룹/주그룹이 있는가? ➔ 통과 (읽기/쓰기 모두 가능)
    4. min_read_rank / min_write_rank 와 사용자 랭킹 비교 ➔ 통과 또는 403 차단
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        allowed = evaluate_permission(
            user=current_user,
            action=action,
            min_read_rank=min_read_rank,
            min_write_rank=min_write_rank,
            allow_groups=allow_groups,
            deny_groups=deny_groups,
            op=op,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다. (그룹 제한 또는 권한 랭킹 부족)"
            )
        return current_user
    return _check
