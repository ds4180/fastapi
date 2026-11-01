"""
============================================================================
[자율신경계 System Watchdog 단위/통합 테스트 (tests/test_watchdog.py)]
============================================================================
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User, UserProfile
from models.system import SystemConfig, SystemTask
from models.audit import AuditLog
from models.miniapp import MiniappItem
from models.alert import Alert
from domain.system.watchdog_service import (
    get_watchdog_settings,
    check_and_alert_task_failure,
    check_and_alert_security_violation,
    check_and_alert_instruction_delays,
    run_watchdog_inspection,
    _COOLDOWN_MAP
)


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    SystemConfig.__table__.create(engine)
    SystemTask.__table__.create(engine)
    AuditLog.__table__.create(engine)
    MiniappItem.__table__.create(engine)
    Alert.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # 최고 관리자 생성
    admin = User(id=1, username="admin_master", email="admin@jeju.live", password="pw", real_name="총괄관리자")
    profile = UserProfile(user_id=1, primary_group="admin")
    session.add_all([admin, profile])
    session.commit()

    # 쿨다운 맵 초기화
    _COOLDOWN_MAP.clear()

    yield session

    session.close()


def test_watchdog_config_defaults_and_override(db_session):
    """기본 설정값 및 DB SystemConfig 오버라이드 검증"""
    # 1. 초기 상태: 기본값
    cfg = get_watchdog_settings(db_session)
    assert cfg["watchdog_enabled"] is True
    assert cfg["watchdog_fail_threshold"] == 3
    assert cfg["watchdog_security_alert"] is True
    assert cfg["watchdog_instruction_delay_minutes"] == 30

    # 2. DB에 커스텀 값 저장
    c1 = SystemConfig(key="watchdog_fail_threshold", value=5)
    c2 = SystemConfig(key="watchdog_enabled", value=False)
    db_session.add_all([c1, c2])
    db_session.commit()

    cfg_updated = get_watchdog_settings(db_session)
    assert cfg_updated["watchdog_fail_threshold"] == 5
    assert cfg_updated["watchdog_enabled"] is False


def test_watchdog_task_failure_alert(db_session):
    """태스크 연속 실패 임계치 도달 시 L4 ALARM 알림 생성 및 쿨다운 검증"""
    now = datetime.now()

    # 1. 실패 2건: 임계치(3) 미만 -> 알림 없음
    t1 = SystemTask(id=1, task_type="TEST", status="FAILED", completed_at=now - timedelta(minutes=10))
    t2 = SystemTask(id=2, task_type="TEST", status="FAILED", completed_at=now - timedelta(minutes=5))
    db_session.add_all([t1, t2])
    db_session.commit()

    assert check_and_alert_task_failure(db_session) is False

    # 2. 실패 3건째 발생: 임계치 도달 -> L4 알림 생성
    t3 = SystemTask(id=3, task_type="TEST", status="FAILED", completed_at=now)
    db_session.add(t3)
    db_session.commit()

    assert check_and_alert_task_failure(db_session, failed_task_id=3) is True

    # MiniappItem에 ALARM 생성 확인
    alarms = db_session.query(MiniappItem).filter(MiniappItem.category == "ALARM").all()
    assert len(alarms) >= 1
    assert "연속 실패" in alarms[0].title
    assert alarms[0].extra_payload.get("level") == 4

    # 3. 쿨다운 검증: 즉시 재호출 시 중복 알림 미발행
    assert check_and_alert_task_failure(db_session) is False


def test_watchdog_disabled_suppresses_alerts(db_session):
    """Watchdog 비활성화 시 임계치 초과해도 알림 억제 검증"""
    db_session.add(SystemConfig(key="watchdog_enabled", value=False))
    now = datetime.now()

    for i in range(1, 6):
        t = SystemTask(id=10 + i, task_type="TEST", status="FAILED", completed_at=now)
        db_session.add(t)
    db_session.commit()

    assert check_and_alert_task_failure(db_session) is False
    alarms = db_session.query(MiniappItem).filter(MiniappItem.category == "ALARM").all()
    assert len(alarms) == 0


def test_watchdog_security_violation_alert(db_session):
    """403 보안 침해 감사로그 발생 시 즉시 L4 경보 발행 검증"""
    audit = AuditLog(
        id=101,
        app_id="admin_rbac",
        log_type="SECURITY",
        severity="CRITICAL",
        action="UNAUTHORIZED_ACCESS_403",
        title="무단 관리자 접근 시도"
    )
    db_session.add(audit)
    db_session.commit()

    res = check_and_alert_security_violation(db_session, audit)
    assert res is True

    alarms = db_session.query(MiniappItem).filter(MiniappItem.category == "ALARM").all()
    assert len(alarms) >= 1
    assert "보안 경보" in alarms[0].title
    assert alarms[0].link == "/v1/admin/observability"


def test_watchdog_instruction_delays(db_session):
    """긴급 현장 지시사항 미확인 지연 감시 검증"""
    now = datetime.now()
    # 40분 전 발행된 지시사항 3건 (PENDING)
    for i in range(3):
        item = MiniappItem(
            sender_id=1,
            receiver_id=10 + i,
            category="INSTRUCTION",
            title=f"지시사항 {i}",
            content="확인바람",
            status="PENDING",
            created_at=now - timedelta(minutes=45)
        )
        db_session.add(item)
    db_session.commit()

    res = check_and_alert_instruction_delays(db_session)
    assert res is True

    alarms = db_session.query(MiniappItem).filter(
        MiniappItem.category == "ALARM",
        MiniappItem.title.like("%현장 지시사항%")
    ).all()
    assert len(alarms) >= 1


def test_run_watchdog_inspection_routine(db_session):
    """Watchdog 종합 자율 점검 루틴 실행 검증"""
    report = run_watchdog_inspection(db_session)
    assert "inspected_at" in report
    assert report["status"] in ["HEALTHY", "ALERTED"]
