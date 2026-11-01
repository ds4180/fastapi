"""
============================================================================
[시스템 데이터 보존 및 가비지 컬렉션(GC) 단위/통합 테스트 (tests/test_retention_gc.py)]
============================================================================
"""

import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User, UserProfile, UserSession
from models.system import SystemConfig, SystemTask
from models.audit import AuditLog
from domain.system.retention_service import (
    get_retention_settings,
    clean_redis_keys,
    run_data_retention_gc
)


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    UserSession.__table__.create(engine)
    SystemConfig.__table__.create(engine)
    SystemTask.__table__.create(engine)
    AuditLog.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    admin = User(id=1, username="admin_master", email="admin@jeju.live", password="pw", real_name="총괄관리자")
    profile = UserProfile(user_id=1, primary_group="admin")
    session.add_all([admin, profile])
    session.commit()

    yield session

    session.close()


def test_retention_config_defaults_and_override(db_session):
    """기본 보존 주기 및 DB 오버라이드 검증"""
    cfg = get_retention_settings(db_session)
    assert cfg["retention_audit_log_days"] == 180
    assert cfg["retention_system_task_days"] == 30
    assert cfg["retention_session_history_days"] == 60
    assert cfg["retention_redis_dynamic_hours"] == 48

    # 커스텀 값 저장
    db_session.add(SystemConfig(key="retention_audit_log_days", value=90))
    db_session.add(SystemConfig(key="retention_redis_dynamic_hours", value=24))
    db_session.commit()

    cfg_updated = get_retention_settings(db_session)
    assert cfg_updated["retention_audit_log_days"] == 90
    assert cfg_updated["retention_redis_dynamic_hours"] == 24


def test_clean_redis_keys():
    """Redis 동적 그룹 TTL 강제 주입 및 고아 키 정리 검증"""
    mock_rd = MagicMock()

    # 메타데이터: today_dayoff(동적), manual_1(수동)
    mock_rd.hgetall.return_value = {
        "today_dayoff": json.dumps({"name": "today_dayoff", "type": "dynamic"}),
        "manual_1": json.dumps({"name": "manual_1", "type": "manual"})
    }

    # 실제 키: today_dayoff, manual_1, orphan_group
    mock_rd.keys.return_value = [
        "group:data:today_dayoff",
        "group:data:manual_1",
        "group:data:orphan_group"
    ]

    # today_dayoff는 TTL이 -1(무기한)
    def mock_ttl(key):
        if key == "group:data:today_dayoff":
            return -1
        return 1000

    mock_rd.ttl.side_effect = mock_ttl

    res = clean_redis_keys(mock_rd, dynamic_ttl_hours=48)

    # 1. today_dayoff에 TTL 강제 적용 확인
    mock_rd.expire.assert_called_with("group:data:today_dayoff", 48 * 3600)
    assert res["ttl_enforced"] == 1

    # 2. 고아 키 orphan_group 삭제 확인
    mock_rd.delete.assert_called_with("group:data:orphan_group")
    assert res["orphans_removed"] == 1


def test_data_retention_db_cleanup(db_session):
    """PostgreSQL 만료 데이터(태스크/세션/감사로그) 자율 삭제 검증"""
    now = datetime.now()

    # 1. SystemTask:
    # - t1: 35일 전 완료된 태스크 (삭제 대상: 보존 30일 초과)
    # - t2: 5일 전 완료된 태스크 (보존 대상)
    # - t3: 40일 전 생성되었으나 아직 PENDING인 태스크 (활성 상태이므로 보존 대상)
    t1 = SystemTask(id=1, task_type="GC", status="SUCCESS", completed_at=now - timedelta(days=35))
    t2 = SystemTask(id=2, task_type="GC", status="FAILED", completed_at=now - timedelta(days=5))
    t3 = SystemTask(id=3, task_type="GC", status="PENDING", created_at=now - timedelta(days=40))

    # 2. UserSession:
    # - s1: 70일 전 로그아웃된 세션 (삭제 대상: 보존 60일 초과)
    # - s2: 10일 전 로그아웃된 세션 (보존 대상)
    # - s3: 100일 전 로그인했으나 현재 ACTIVE 상태인 세션 (보존 대상)
    s1 = UserSession(user_id=1, session_key="key-old", device_category="DESKTOP", status="LOGOUT", login_at=now - timedelta(days=70))
    s2 = UserSession(user_id=1, session_key="key-recent", device_category="DESKTOP", status="KICKED_OUT", login_at=now - timedelta(days=10))
    s3 = UserSession(user_id=1, session_key="key-active", device_category="DESKTOP", status="ACTIVE", login_at=now - timedelta(days=100))

    # 3. AuditLog:
    # - a1: 200일 전 감사로그 (삭제 대상: 보존 180일 초과)
    # - a2: 30일 전 감사로그 (보존 대상)
    a1 = AuditLog(id=1, app_id="test", log_type="ACCESS", title="오래된 로그", action="LOGIN", created_at=now - timedelta(days=200))
    a2 = AuditLog(id=2, app_id="test", log_type="SECURITY", title="최근 로그", action="403", created_at=now - timedelta(days=30))

    db_session.add_all([t1, t2, t3, s1, s2, s3, a1, a2])
    db_session.commit()

    # GC 실행
    report = run_data_retention_gc(db_session, rd=None)

    assert report["status"] == "SUCCESS"
    assert report["deleted_tasks"] == 1
    assert report["deleted_sessions"] == 1
    assert report["deleted_audit_logs"] == 1

    # 남아있는 레코드 검증
    remaining_tasks = [t.id for t in db_session.query(SystemTask).all()]
    assert remaining_tasks == [2, 3]

    remaining_sessions = [s.session_key for s in db_session.query(UserSession).all()]
    assert set(remaining_sessions) == {"key-recent", "key-active"}

    remaining_audits = [a.id for a in db_session.query(AuditLog).all() if a.id in [1, 2]]
    assert remaining_audits == [2]

    # GC 수행 기록 자체가 감사로그에 등록되었는지 확인
    gc_audit = db_session.query(AuditLog).filter(AuditLog.action == "DATA_RETENTION_GC").first()
    assert gc_audit is not None
