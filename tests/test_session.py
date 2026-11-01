"""
============================================================================
[테스트 3: 세션 엔진 및 디바이스 판별 검사 (tests/test_session.py)]
============================================================================

💡 이 테스트의 목적:
`core/session.py` 엔진이 사용자의 접속 브라우저(User-Agent)를 읽고,
모바일(아이폰/안드로이드)과 데스크톱(PC)을 오차 없이 칼같이 분류해 내는지 검증합니다.
"""

from core.session import detect_device_category


def test_device_category_detection():
    """
    [검사 1] User-Agent 헤더에 따라 MOBILE과 DESKTOP이 정확히 구분되는가?
    """
    # 📱 모바일 디바이스 예시들
    iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15"
    android_ua = "Mozilla/5.0 (Linux; Android 13; SM-S908N) AppleWebKit/537.36 Mobile Safari/537.36"

    assert detect_device_category(iphone_ua) == "MOBILE", "아이폰 접속을 모바일로 인식하지 못했습니다."
    assert detect_device_category(android_ua) == "MOBILE", "안드로이드 접속을 모바일로 인식하지 못했습니다."

    # 💻 PC 데스크톱 디바이스 예시들
    windows_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0"
    mac_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36"

    assert detect_device_category(windows_ua) == "DESKTOP", "윈도우 PC 접속을 데스크톱으로 인식하지 못했습니다."
    assert detect_device_category(mac_ua) == "DESKTOP", "맥북 PC 접속을 데스크톱으로 인식하지 못했습니다."


def test_validate_session_self_healing(monkeypatch):
    """
    [검사 2] Redis 재부팅 등으로 키가 유실되었더라도,
    DB가 ACTIVE 상태라면 세션을 파괴(EXPIRED)하지 않고 Redis에 키를 자가 치유(Self-Healing) 등록하는가?
    """
    from unittest.mock import MagicMock
    from models import User, UserProfile, UserSession
    from core.session import validate_session

    # 1. 가상 DB 세션 및 유저 세트 준비
    user = User(id=99, username="tester", email="tester@jeju.live")
    user.profile = UserProfile(rank_level=2)
    session_record = UserSession(
        user_id=99,
        session_key="test-jti-uuid",
        device_category="DESKTOP",
        status="ACTIVE",
    )
    session_record.user = user

    mock_db = MagicMock()
    # db.query(UserSession).options(...).filter(...).first() 체인 모킹
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = session_record

    # 2. Redis 모킹 (처음 sismember는 False로 메모리 휘발 상황 시뮬레이션)
    mock_rd = MagicMock()
    mock_rd.sismember.return_value = False
    monkeypatch.setattr("core.session.rd", mock_rd)

    # 3. 세션 검증 실행
    validated_user = validate_session(mock_db, "test-jti-uuid")

    # 4. 검증:
    # - 유저가 정상 반환되어야 함 (로그아웃 안 됨!)
    assert validated_user is not None
    assert validated_user.username == "tester"
    # - DB 상태가 EXPIRED로 덮어써지지 않고 여전히 ACTIVE 유지
    assert session_record.status == "ACTIVE"
    # - Redis에 해당 키가 자가 치유로 다시 sadd 되었는지 확인
    mock_rd.sadd.assert_called_once_with("session:99:DESKTOP", "test-jti-uuid")
    mock_rd.expire.assert_called_once()

