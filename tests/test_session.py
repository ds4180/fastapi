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


def test_validate_session_expires_after_inactivity(monkeypatch):
    """
    [비활동 만료 통합 검증]:
    last_activity(또는 login_at)가 SESSION_EXPIRE_DAYS(3일)를 초과하면
    Redis 상태와 무관하게 DB 상태를 EXPIRED로 전환하고 None을 반환해야 한다.
    """
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from models import User, UserSession
    from core.session import validate_session, SESSION_EXPIRE_DAYS

    mock_db = MagicMock()
    mock_user = User(id=99, username="tester")
    stale_time = datetime.now() - timedelta(days=SESSION_EXPIRE_DAYS, minutes=5)
    session_record = UserSession(
        user_id=99,
        session_key="stale-jti-uuid",
        device_category="DESKTOP",
        status="ACTIVE",
        last_activity=stale_time,
        login_at=stale_time,
        user=mock_user,
    )
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = session_record

    mock_rd = MagicMock()
    mock_rd.sismember.return_value = True
    monkeypatch.setattr("core.session.rd", mock_rd)

    validated_user = validate_session(mock_db, "stale-jti-uuid")

    assert validated_user is None
    assert session_record.status == "EXPIRED"
    assert session_record.logout_at is not None
    mock_rd.srem.assert_called_once_with("session:99:DESKTOP", "stale-jti-uuid")
    mock_db.commit.assert_called_once()


def test_validate_session_marks_cookie_renewal_on_activity_threshold(monkeypatch):
    """
    [브라우저 쿠키 슬라이딩 윈도우 트리거 검증]:
    마지막 활동으로부터 5분(ACTIVITY_UPDATE_INTERVAL_SECONDS) 이상 경과 후 유효 요청이 오면
    DB last_activity를 갱신하고 request.state.renew_session_id를 설정해야 한다.
    """
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from fastapi import Request
    from models import User, UserSession
    from core.session import validate_session, ACTIVITY_UPDATE_INTERVAL_SECONDS

    mock_db = MagicMock()
    mock_user = User(id=99, username="tester")
    prev_activity = datetime.now() - timedelta(seconds=ACTIVITY_UPDATE_INTERVAL_SECONDS + 30)
    session_record = UserSession(
        user_id=99,
        session_key="sliding-jti-uuid",
        device_category="DESKTOP",
        status="ACTIVE",
        last_activity=prev_activity,
        login_at=prev_activity,
        user=mock_user,
    )
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = session_record

    mock_rd = MagicMock()
    mock_rd.sismember.return_value = True
    monkeypatch.setattr("core.session.rd", mock_rd)

    req = Request({"type": "http", "headers": []})
    validated_user = validate_session(mock_db, "sliding-jti-uuid", request=req)

    assert validated_user is mock_user
    assert getattr(req.state, "renew_session_id", None) == "sliding-jti-uuid"
    assert session_record.last_activity > prev_activity
    mock_db.commit.assert_called_once()


def test_get_session_list_uses_self_healing_instead_of_destructive_expire(monkeypatch):
    """
    [레거시 파괴적 동기화 제거 검증]:
    user_crud.get_session_list() 호출 시 Redis에 키가 없더라도 유효 기간 내 ACTIVE 세션이면
    EXPIRED로 파괴하지 않고 Redis 키를 자가치유(Self-Healing) 복원해야 한다.
    """
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from models import User, UserSession
    from domain.user import user_crud

    mock_db = MagicMock()
    alice = User(id=7, username="alice")
    recent_time = datetime.now() - timedelta(hours=2)
    active_session = UserSession(
        user_id=7,
        session_key="heal-jti-uuid",
        device_category="MOBILE",
        status="ACTIVE",
        last_activity=recent_time,
        login_at=recent_time,
        user=alice,
    )

    mock_db.query.return_value.filter.return_value.all.return_value = [active_session]
    mock_db.query.return_value.join.return_value.order_by.return_value.limit.return_value.all.return_value = [
        active_session
    ]

    mock_rd = MagicMock()
    mock_rd.sismember.return_value = False
    monkeypatch.setattr("core.session.rd", mock_rd)

    sessions = user_crud.get_session_list(mock_db)

    assert len(sessions) == 1
    assert sessions[0].username == "alice"
    assert active_session.status == "ACTIVE"
    mock_rd.sadd.assert_called_once_with("session:7:MOBILE", "heal-jti-uuid")


def test_middleware_sets_sliding_cookie_header():
    """
    [RequestIDMiddleware 슬라이딩 Set-Cookie 응답 헤더 검증]:
    - 200 정상 응답 + renew_session_id 존재 시 Set-Cookie: session_id=... Max-Age 발급
    - session_terminated=True(로그아웃) 또는 4xx 응답에서는 슬라이딩 Set-Cookie 미발급
    """
    from fastapi import FastAPI, Request, Response
    from fastapi.testclient import TestClient
    from core.middleware import RequestIDMiddleware
    from core.session import SESSION_EXPIRE_SECONDS

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ok")
    def ok_route(request: Request):
        request.state.renew_session_id = "sliding-jti-uuid"
        return {"ok": True}

    @app.post("/logout")
    def logout_route(request: Request, response: Response):
        request.state.renew_session_id = "sliding-jti-uuid"
        request.state.session_terminated = True
        response.delete_cookie("session_id", path="/")
        return {"ok": True}

    @app.get("/err")
    def err_route(request: Request):
        request.state.renew_session_id = "sliding-jti-uuid"
        return Response(status_code=401)

    client = TestClient(app)

    res_ok = client.get("/ok")
    assert res_ok.status_code == 200
    ok_cookie = res_ok.headers.get("set-cookie", "")
    assert "session_id=sliding-jti-uuid" in ok_cookie
    assert f"Max-Age={SESSION_EXPIRE_SECONDS}" in ok_cookie

    res_logout = client.post("/logout")
    assert res_logout.status_code == 200
    assert "sliding-jti-uuid" not in res_logout.headers.get("set-cookie", "")

    res_err = client.get("/err")
    assert res_err.status_code == 401
    assert "set-cookie" not in res_err.headers


def test_get_client_ip_extracts_forwarded_headers():
    """SvelteKit SSR 및 리버스 프록시 환경에서 X-Forwarded-For / X-Real-IP 실제 IP 추출 검증"""
    from unittest.mock import MagicMock
    from core.session import get_client_ip

    req_xff = MagicMock()
    req_xff.headers = {"x-forwarded-for": "203.0.113.10, 172.18.0.5"}
    req_xff.client.host = "172.18.0.5"
    assert get_client_ip(req_xff) == "203.0.113.10"

    req_real = MagicMock()
    req_real.headers = {"x-real-ip": "198.51.100.22"}
    req_real.client.host = "172.18.0.5"
    assert get_client_ip(req_real) == "198.51.100.22"

    req_direct = MagicMock()
    req_direct.headers = {}
    req_direct.client.host = "127.0.0.1"
    assert get_client_ip(req_direct) == "127.0.0.1"


def test_login_rate_limit_and_lockout(monkeypatch):
    """Redis 기반 무차별 대입(Brute-Force) 방어 카운터, 잠금 판별 및 감사 로그 검증"""
    from unittest.mock import MagicMock
    from core.config import settings
    from core.session import (
        check_login_rate_limit,
        record_login_failure,
        clear_login_failures,
    )

    mock_db = MagicMock()
    mock_rd = MagicMock()
    mock_audit = MagicMock()
    monkeypatch.setattr("core.session.rd", mock_rd)
    monkeypatch.setattr("core.session.safe_log_audit", mock_audit)

    # 1. 정상 허용 상태 (실패 이력 없음 -> None 반환)
    mock_rd.get.side_effect = [None, None]
    assert check_login_rate_limit("alice", "203.0.113.10") is None

    # 2. 계정+IP 임계치(5회) 도달 시 남은 잠금 대기 시간(int) 반환
    mock_rd.get.side_effect = ["2", str(settings.LOGIN_MAX_ATTEMPTS)]
    mock_rd.ttl.return_value = 240
    retry_after = check_login_rate_limit("alice", "203.0.113.10")
    assert retry_after == 240

    # 3. 5번째 실패 기록 시 SECURITY/CRITICAL 감사 로그(Watchdog 연동) 발생 검증
    mock_rd.incr.side_effect = [settings.LOGIN_MAX_ATTEMPTS, 5]
    mock_rd.ttl.return_value = 280
    attempts, lockout_sec = record_login_failure(mock_db, "alice", "203.0.113.10")
    assert attempts == settings.LOGIN_MAX_ATTEMPTS
    assert lockout_sec == 280
    mock_audit.assert_called_once()
    _, kwargs = mock_audit.call_args
    assert kwargs["log_type"] == "SECURITY"
    assert kwargs["severity"] == "CRITICAL"
    assert kwargs["action"] == "LOGIN_LOCKOUT"

    # 4. 로그인 성공 시 계정+IP 및 단일 IP 실패 카운터 초기화 검증
    clear_login_failures("alice", "203.0.113.10")
    mock_rd.delete.assert_called_once_with(
        "login_fail:user:alice:203.0.113.10",
        "login_fail:ip:203.0.113.10",
    )


def test_verify_user_credentials_constant_time():
    """존재하지 않는 사용자(user=None) 로그인 시도 시에도 더미 해시 검증을 수행하는지 확인"""
    from unittest.mock import patch
    from domain.user import user_crud

    with patch.object(user_crud.pwd_context, "verify", wraps=user_crud.pwd_context.verify) as spy_verify:
        result = user_crud.verify_user_credentials(None, "any-password-123")
        assert result is False
        spy_verify.assert_called_once_with("any-password-123", user_crud.DUMMY_PASSWORD_HASH)


def test_validate_session_revokes_deactivated_user_and_device_mismatch(monkeypatch):
    """비활성화 계정(is_active=False) 즉시 차단 및 기기 카테고리 불일치(쿠키 탈취) 차단 검증"""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from models import User, UserProfile, UserSession
    from core.session import validate_session

    mock_db = MagicMock()
    mock_rd = MagicMock()
    mock_rd.sismember.return_value = True
    monkeypatch.setattr("core.session.rd", mock_rd)
    monkeypatch.setattr("core.session.safe_log_audit", MagicMock())

    now = datetime.now()

    # 1. 비활성화 계정(is_active=False) 실시간 차단 검증
    deactivated_user = User(id=10, username="suspended")
    deactivated_user.profile = UserProfile(rank_level=2, is_active=False)
    deactivated_session = UserSession(
        user_id=10,
        session_key="deactivated-jti",
        device_category="DESKTOP",
        status="ACTIVE",
        login_at=now - timedelta(minutes=10),
        last_activity=now - timedelta(minutes=1),
        user=deactivated_user,
    )
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = deactivated_session

    assert validate_session(mock_db, "deactivated-jti") is None
    assert deactivated_session.status == "KICKED_OUT"
    mock_rd.srem.assert_called_with("session:10:DESKTOP", "deactivated-jti")

    # 2. 기기 카테고리 바인딩(DESKTOP 세션 쿠키를 MOBILE 브라우저에서 재사용) 차단 검증
    active_user = User(id=11, username="active_user")
    active_user.profile = UserProfile(rank_level=2, is_active=True)
    desktop_session = UserSession(
        user_id=11,
        session_key="Hijacked-desktop-jti",
        device_category="DESKTOP",
        status="ACTIVE",
        login_at=now - timedelta(minutes=10),
        last_activity=now - timedelta(minutes=1),
        user=active_user,
    )
    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = desktop_session
    mock_rd.srem.reset_mock()

    mobile_req = MagicMock()
    mobile_req.headers = {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
    }
    mobile_req.client.host = "203.0.113.55"

    assert validate_session(mock_db, "Hijacked-desktop-jti", request=mobile_req) is None
    assert desktop_session.status == "KICKED_OUT"
    mock_rd.srem.assert_called_once_with("session:11:DESKTOP", "Hijacked-desktop-jti")



