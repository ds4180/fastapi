"""
============================================================================
[백엔드 코어 표준 예외 분류 체계 (core/exceptions.py)]
============================================================================

💡 이 파일의 역할:
FastAPI 엔드포인트와 비즈니스 서비스 계층에서 발생하는 모든 에러를
의미 있는 6대 표준 예외 클래스로 분류하고 통일된 응답 규격을 제공합니다.

🌟 장점:
1. `raise HTTPException(status_code=403, detail="...")` 같은 마술 숫자를 전면 퇴출합니다.
2. 모든 에러가 일관된 JSON 에러 규격(Error Envelope)을 갖추어 프론트엔드 연동이 완벽해집니다.
3. 403(권한 거부)이 500(서버 고장)으로 둔갑하는 예외 마스킹 버그를 원천 차단합니다.
4. 보안 감사로그(Audit Log)와 연동되어 비정상 침해 시도를 자동으로 색인합니다.
"""

from datetime import datetime
from typing import Optional, Any, Dict
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class CoreException(HTTPException):
    """
    [플랫폼 코어 기본 예외 클래스]
    FastAPI의 HTTPException을 상속받아, 별도 전역 핸들러 없이도
    기본 4xx/5xx HTTP 응답으로 안전하게 변환됩니다.
    """
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Any] = None,
        resource: Optional[str] = None,
        resource_id: Optional[Any] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = error_code
        self.message = message
        self.details = details
        self.resource = resource
        self.resource_id = resource_id
        self.timestamp = datetime.now().isoformat()

    @property
    def code(self) -> str:
        """하위 호환성을 위한 error_code 별칭 프로퍼티 (AttributeError 원천 차단)"""
        return self.error_code

    def to_dict(self) -> Dict[str, Any]:
        """프론트엔드 표준 통신 규격에 맞춘 에러 딕셔너리 반환"""
        error_data = {
            "code": self.error_code,
            "status": self.status_code,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.resource:
            error_data["resource"] = self.resource
        if self.resource_id is not None:
            error_data["resource_id"] = str(self.resource_id)
        if self.details is not None:
            error_data["details"] = self.details

        return {
            "success": False,
            "error": error_data,
            # Legacy 하위 호환성을 위해 detail 필드도 최상위에 함께 유지
            "detail": self.message,
        }

    def to_response(self) -> JSONResponse:
        """FastAPI 표준 JSONResponse 객체 생성"""
        return JSONResponse(
            status_code=self.status_code,
            content=self.to_dict(),
        )


# ============================================================================
# 🏛️ 코어 6대 표준 예외 클래스 (Taxonomy)
# ============================================================================

class AuthenticationRequiredError(CoreException):
    """
    [401 Unauthorized] 로그인이 필요한 엔드포인트에 비로그인 손님이 접근했을 때 발생
    """
    def __init__(self, message: str = "로그인이 필요한 서비스입니다.", **kwargs):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_REQUIRED",
            message=message,
            **kwargs,
        )


class SessionExpiredError(CoreException):
    """
    [401 Unauthorized] 세션이 만료되었거나 다른 기기에서 중복 로그인되어 추방(KICKED_OUT)되었을 때 발생
    """
    def __init__(
        self,
        message: str = "세션이 만료되었거나 다른 기기에서 로그인하여 접속이 종료되었습니다.",
        **kwargs,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="SESSION_EXPIRED",
            message=message,
            **kwargs,
        )


class AccessDeniedError(CoreException):
    """
    [403 Forbidden] 신분(로그인)은 확인되었으나 권한 랭킹(0~9) 또는 부서/그룹 권한이 부족할 때 발생
    💡 500 에러로 마스킹되지 않고 클라이언트에 정확한 권한 부족 안내를 전달합니다.
    """
    def __init__(
        self,
        message: str = "해당 기능에 접근할 권한이 없습니다.",
        resource: Optional[str] = None,
        resource_id: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCESS_DENIED",
            message=message,
            resource=resource,
            resource_id=resource_id,
            **kwargs,
        )


class ResourceNotFoundError(CoreException):
    """
    [404 Not Found] 요청한 게시판, 게시글, 페이지, 배차 노선 등의 데이터가 존재하지 않을 때 발생
    """
    def __init__(
        self,
        message: str = "요청하신 리소스를 찾을 수 없습니다.",
        resource: Optional[str] = None,
        resource_id: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            message=message,
            resource=resource,
            resource_id=resource_id,
            **kwargs,
        )


class ResourceConflictError(CoreException):
    """
    [409 Conflict] 중복된 ID/Slug 등록, 동일 차량의 중복 배정, 동시 수정 경합 발생 시 발생
    """
    def __init__(
        self,
        message: str = "이미 존재하는 데이터이거나 동시 작업 충돌이 발생했습니다.",
        resource: Optional[str] = None,
        resource_id: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            message=message,
            resource=resource,
            resource_id=resource_id,
            **kwargs,
        )


class BusinessRuleError(CoreException):
    """
    [422 Unprocessable Entity] 휴무 신청 마감 기한 초과, 최대 정원 초과 등 비즈니스 제약 위배 시 발생
    """
    def __init__(
        self,
        message: str = "업무 처리 규칙을 위배하여 요청을 완료할 수 없습니다.",
        rule_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            error_code="BUSINESS_RULE_VIOLATION",
            message=message,
            details={"rule": rule_name} if rule_name else None,
            **kwargs,
        )
