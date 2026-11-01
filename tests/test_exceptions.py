"""
============================================================================
[테스트 5: 코어 표준 예외 분류 체계 및 응답 규격 검사 (tests/test_exceptions.py)]
============================================================================

💡 이 테스트의 목적:
`core/exceptions.py`의 6대 표준 예외 클래스가 올바른 HTTP 상태 코드와
고유 에러 코드(Code), 표준 에러 규격(Envelope)을 갖추고 있는지 기계적으로 검증합니다.
"""

from core.exceptions import (
    CoreException,
    AuthenticationRequiredError,
    SessionExpiredError,
    AccessDeniedError,
    ResourceNotFoundError,
    ResourceConflictError,
    BusinessRuleError,
)


def test_core_exceptions_status_and_code():
    """
    [검사 1] 6대 표준 예외의 HTTP 상태 코드 및 고유 에러 코드가 표준과 일치하는가?
    """
    # 1. 401 인증 필요
    e_auth = AuthenticationRequiredError("로그인이 필요합니다.")
    assert e_auth.status_code == 401
    assert e_auth.error_code == "AUTH_REQUIRED"

    # 2. 401 세션 만료
    e_session = SessionExpiredError("세션이 만료되었습니다.")
    assert e_session.status_code == 401
    assert e_session.error_code == "SESSION_EXPIRED"

    # 3. 403 권한 거부
    e_denied = AccessDeniedError("게시판 열람 권한이 없습니다.", resource="board", resource_id="notice")
    assert e_denied.status_code == 403
    assert e_denied.error_code == "ACCESS_DENIED"
    assert e_denied.resource == "board"
    assert e_denied.resource_id == "notice"

    # 4. 404 리소스 없음
    e_not_found = ResourceNotFoundError("페이지를 찾을 수 없습니다.", resource="page", resource_id=123)
    assert e_not_found.status_code == 404
    assert e_not_found.error_code == "NOT_FOUND"

    # 5. 409 충돌
    e_conflict = ResourceConflictError("동일 노선에 이미 기사가 배정되어 있습니다.")
    assert e_conflict.status_code == 409
    assert e_conflict.error_code == "CONFLICT"

    # 6. 422 비즈니스 룰 위배
    e_rule = BusinessRuleError("휴무 신청 가능 일수를 초과했습니다.", rule_name="MAX_DAYOFF_LIMIT")
    assert e_rule.status_code == 422
    assert e_rule.error_code == "BUSINESS_RULE_VIOLATION"
    assert e_rule.details == {"rule": "MAX_DAYOFF_LIMIT"}


def test_standard_error_envelope_format():
    """
    [검사 2] to_dict() 호출 시 프론트엔드가 요구하는 표준 JSON 규격(Envelope)을 완벽히 생성하는가?
    """
    err = AccessDeniedError(
        message="비공개 문서입니다.",
        resource="document",
        resource_id="doc-99"
    )
    data = err.to_dict()

    assert data["success"] is False
    assert "error" in data
    assert data["error"]["code"] == "ACCESS_DENIED"
    assert data["error"]["status"] == 403
    assert data["error"]["message"] == "비공개 문서입니다."
    assert data["error"]["resource"] == "document"
    assert data["error"]["resource_id"] == "doc-99"
    assert "timestamp" in data["error"]
    # Legacy 하위 호환성을 위해 detail 필드도 유지되는지 확인
    assert data["detail"] == "비공개 문서입니다."
