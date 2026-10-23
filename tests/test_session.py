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
