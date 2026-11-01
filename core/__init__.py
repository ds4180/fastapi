"""
[제주 라이브 백엔드 코어 패키지 (core)]
- config.py: 중앙 환경변수 및 시스템 전역 설정
- session.py: Redis JTI 멀티디바이스 세션 관리 및 자가 치유 엔진
- permission.py: 리눅스식 그룹 × 랭킹(0~9) 4단계 인가 엔진
- deps.py: FastAPI 공통 의존성 주입 사령탑
- exceptions.py: 코어 6대 표준 예외 체계 (Taxonomy)
"""

from core.config import settings
from core.middleware import RequestIDMiddleware
from core.notify import notify, safe_notify
from core.exceptions import (
    CoreException,
    AuthenticationRequiredError,
    SessionExpiredError,
    AccessDeniedError,
    ResourceNotFoundError,
    ResourceConflictError,
    BusinessRuleError,
)
