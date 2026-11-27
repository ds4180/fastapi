"""
Web Push 타임아웃/스레드풀 및 WebAuthn 챌린지 원자 소비·Origin 검증 테스트 (tests/test_push_biometric_security.py)
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.push import push_router, push_service
from domain.v1.biometric import biometric_router


def test_webpush_enforces_timeout_and_push_routes_are_sync(monkeypatch):
    """_dispatch_push가 webpush 호출 시 timeout을 전달하고 push 라우터들이 sync def인지 검증"""
    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(push_service, "webpush", fake_webpush)
    sub = SimpleNamespace(id=1, endpoint="https://fcm.example/abc", p256dh="k1", auth="a1")
    res = push_service._dispatch_push(MagicMock(), [sub], "제목", "내용", "/")

    assert res["sent"] == 1
    assert captured.get("timeout") == push_service.WEBPUSH_TIMEOUT_SEC
    assert captured.get("timeout") > 0

    for fn in (
        push_router.subscribe_push_notification,
        push_router.unsubscribe_push_notification,
        push_router.send_all_push_notifications,
    ):
        assert not inspect.iscoroutinefunction(fn)


def test_biometric_origin_whitelist_and_atomic_getdel(monkeypatch):
    """허용되지 않은 WebAuthn Origin 차단(400) 및 Redis getdel 원자 소비 검증"""
    bad_req = SimpleNamespace(headers={"origin": "https://evil.attacker.com"}, url=SimpleNamespace(scheme="https", netloc="evil.attacker.com"))
    with pytest.raises(HTTPException) as exc:
        biometric_router._resolve_rp_and_origin(bad_req)
    assert exc.value.status_code == 400

    ok_req = SimpleNamespace(headers={"origin": "https://www.jeju.live"}, url=SimpleNamespace(scheme="https", netloc="www.jeju.live"))
    rp_id, origin = biometric_router._resolve_rp_and_origin(ok_req)
    assert rp_id == "jeju.live"
    assert origin == "https://www.jeju.live"

    # Redis getdel 호출 검증
    called = {"getdel": 0}

    class FakeRedis:
        def getdel(self, key):
            called["getdel"] += 1
            return "AQID" if called["getdel"] == 1 else None

    monkeypatch.setattr(biometric_router, "_get_redis", lambda: FakeRedis())
    first = biometric_router._pop_challenge("auth", 99)
    second = biometric_router._pop_challenge("auth", 99)
    assert first == b"\x01\x02\x03"
    assert second is None
    assert called["getdel"] == 2
