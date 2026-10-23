"""
============================================================================
[테스트 2: 보안 및 비밀번호 암호화 검사 (tests/test_security.py)]
============================================================================

💡 이 테스트의 목적:
우리가 레거시 `passlib` 대신 적용한 최신 표준 `pwdlib` 모듈이
비밀번호를 안전하게 단방향 해싱(암호화)하고, 일치 여부를 정확히 판별하는지 검증합니다.
"""

from domain.user.user_crud import pwd_context


def test_password_hashing_and_verification():
    """
    [검사 1] 비밀번호가 올바르게 암호화되고, 원래 비밀번호와 정확히 대조되는가?
    """
    plain_password = "MySecurePassword123!"

    # 1. 비밀번호 암호화 (해시 생성)
    hashed_password = pwd_context.hash(plain_password)

    # 암호화된 비밀번호는 평문과 달라야 하며, bcrypt 규격($2b$)으로 시작해야 합니다.
    assert hashed_password != plain_password, "비밀번호가 평문 그대로 노출되었습니다!"
    assert hashed_password.startswith("$2b$"), "bcrypt 알고리즘 형식($2b$)이 아닙니다!"

    # 2. 올바른 비밀번호로 검증 -> 결과가 True 여야 통과!
    is_correct = pwd_context.verify(plain_password, hashed_password)
    assert is_correct is True, "올바른 비밀번호인데 검증에 실패했습니다."

    # 3. 틀린 비밀번호로 검증 -> 결과가 False 여야 통과!
    is_wrong = pwd_context.verify("WrongPassword999", hashed_password)
    assert is_wrong is False, "틀린 비밀번호인데 통과되는 치명적 보안 결함이 발생했습니다!"
