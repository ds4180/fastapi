"""
휴무·배차 핵심 비즈니스 로직 및 알림 토글·익일 보호 검증 테스트 (tests/test_dayoff_dispatch_integrity.py)
"""

import importlib
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.dayoff import dayoff_admin_router, dayoff_router, dayoff_schema
from domain.v1.dispatch import dispatch_daily_router


def test_dayoff_create_notifies_on_requested_and_respects_toggle(monkeypatch):
    """허가제(REQUESTED) 휴무 신청 시 알림이 발송되고, etc.notify_on_request=False면 차단되는지 검증"""
    sent = []
    notify_mod = importlib.import_module("core.notify")
    push_mod = importlib.import_module("domain.push.push_service")

    monkeypatch.setattr(dayoff_router.dayoff_crud, "create_dayoff_list", lambda db, req, uid: 1)
    monkeypatch.setattr(dayoff_router, "safe_log_audit", lambda **kwargs: None)
    monkeypatch.setattr(notify_mod, "safe_notify", lambda **kwargs: sent.append(kwargs))
    monkeypatch.setattr(push_mod, "is_push_domain_enabled", lambda db, k: True)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = (123,)

    user = SimpleNamespace(id=7, username="staff1", real_name="김사무")
    req = dayoff_schema.DayOffCreate(type=dayoff_schema.DayOffType.ANNUAL, dates=[date.today() + timedelta(days=3)])

    # 1. 토글 ON (기본값) -> 알림 발송됨
    monkeypatch.setattr(
        dayoff_router.dayoff_policy_service,
        "get_dayoff_policy",
        lambda db: {"etc": {"notify_on_request": True}},
    )
    dayoff_router.dayoff_create(req, db=db, current_user=user)
    assert len(sent) == 1
    assert sent[0]["target_app_id"] == "dayoff"

    # 2. 토글 OFF -> 알림 발송 안 됨
    sent.clear()
    monkeypatch.setattr(
        dayoff_router.dayoff_policy_service,
        "get_dayoff_policy",
        lambda db: {"etc": {"notify_on_request": False}},
    )
    dayoff_router.dayoff_create(req, db=db, current_user=user)
    assert len(sent) == 0


def test_admin_update_dayoff_status_validation_audit_and_toggle(monkeypatch):
    """잘못된 상태값 400 차단, 삭제 건 404 차단, 감사로그 기록, notify_on_result 토글 검증"""
    admin = SimpleNamespace(id=1, username="admin")
    db = MagicMock()

    # 1. 허용되지 않은 상태값 -> 400
    with pytest.raises(HTTPException) as exc_400:
        dayoff_admin_router.admin_update_dayoff_status(10, {"status": "BOGUS"}, db=db, admin=admin)
    assert exc_400.value.status_code == 400

    # 2. 삭제되었거나 없는 건 -> 404
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc_404:
        dayoff_admin_router.admin_update_dayoff_status(999, {"status": "APPROVED"}, db=db, admin=admin)
    assert exc_404.value.status_code == 404

    # 3. 정상 승인 시 감사로그 기록 + 토글 OFF일 때 알림 미발송
    audits = []
    notifies = []
    notify_mod = importlib.import_module("core.notify")
    row = SimpleNamespace(id=10, user_id=5, date=date.today(), status="REQUESTED", group_id=None, is_deleted=False)
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(dayoff_admin_router, "safe_log_audit", lambda **kwargs: audits.append(kwargs))
    monkeypatch.setattr(dayoff_admin_router, "get_dayoff_policy", lambda db: {"etc": {"notify_on_result": False}})
    monkeypatch.setattr(notify_mod, "safe_notify", lambda **kwargs: notifies.append(kwargs))

    res = dayoff_admin_router.admin_update_dayoff_status(10, {"status": "APPROVED"}, db=db, admin=admin)
    assert res["new_status"] == "APPROVED"
    assert row.status == "APPROVED"
    assert len(audits) == 1
    assert len(notifies) == 0


def test_save_daily_dispatch_protects_confirmed_tomorrow(monkeypatch):
    """금일 배차 저장 시 이미 CONFIRMED된 익일 배차의 기사 배정이 삭제되지 않고 보호되는지 검증"""
    from domain.v1.dispatch import dispatch_service

    today = date.today()
    tomorrow = today + timedelta(days=1)

    today_row = SimpleNamespace(
        target_date=today,
        timetable_id=1,
        driver_name="홍길동",
        vehicle_no="1001",
        start_time="06:00",
        status="CONFIRMED",
        memo="",
    )
    tomorrow_row = SimpleNamespace(
        target_date=tomorrow,
        timetable_id=1,
        driver_name="김철수",
        vehicle_no="1002",
        start_time="06:00",
        status="CONFIRMED",
        memo="",
    )

    call_idx = {"n": 0}

    def fake_first():
        call_idx["n"] += 1
        return today_row if call_idx["n"] == 1 else tomorrow_row

    db = MagicMock()
    db.bind = None
    db.query.return_value.filter.return_value.first.side_effect = fake_first

    monkeypatch.setattr(dispatch_service, "is_date_published", lambda db, d: False)
    monkeypatch.setattr(dispatch_service, "invalidate_driver_work_stats_cache", lambda: None)
    monkeypatch.setattr(dispatch_daily_router, "load_drivers_metadata", lambda: ({}, {}, {}))

    payload = SimpleNamespace(
        target_date=today,
        status="CONFIRMED",
        rows=[
            SimpleNamespace(
                timetable_id=1,
                driver_name="홍길동",
                vehicle_no="1001",
                start_time="06:00",
                tomorrow_driver_name="",  # 비어있어도 이미 CONFIRMED된 익일 배차는 건드리면 안 됨!
                memo="수정",
            )
        ],
    )
    admin = SimpleNamespace(id=1, username="admin")
    res = dispatch_daily_router.save_daily_dispatch(payload, db=db, admin=admin)
    assert res == {"message": "success"}
    assert tomorrow_row.driver_name == "김철수"
