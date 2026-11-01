"""
============================================================================
[테스트: 시스템 앱 17종 부트스트랩 및 독립 권한 배분 무결성 검증 (tests/test_system_apps_bootstrap.py)]
============================================================================

💡 이 테스트의 목적:
1. 서버 부트스트랩 시 17종 시스템 앱(admin_*)이 app_registry 테이블에 멱등하게 등록되는지 검증
2. 관리자가 특정 시스템 앱(예: 알림 관리, 미디어 관제, 타겟 그룹)에 allow_groups를 지정했을 때,
   랭크가 낮은 사원(Lv.2)도 Allow-Wins 원칙에 따라 정상 접근 가능한지 검증
3. 코어 인프라(admin_config, admin_tasks)는 Lv.8 이상 또는 root(Lv.9)만 접근 가능한지 검증
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models import User, UserProfile, AppRegistry
from domain.system.app_service import bootstrap_system_apps, DEFAULT_SYSTEM_APPS
from core.permission import can_access_app


@pytest.fixture
def db_session():
    """인메모리 SQLite 격리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _make_user(username: str, rank: int, primary_group=None, secondary_groups=None) -> User:
    """테스트용 가상 유저 생성"""
    u = User(username=username, email=f"{username}@jeju.live")
    u.profile = UserProfile(
        rank_level=rank,
        primary_group=primary_group,
        secondary_groups=secondary_groups or [],
    )
    return u


def test_system_apps_bootstrap_idempotency(db_session):
    """
    [검증 1] 시스템 앱 17종 최초 부트스트랩 및 멱등성(재실행 시 중복 방지) 검증
    """
    # 1회차: 17개 전수 생성
    result1 = bootstrap_system_apps(db_session)
    assert result1["created"] == 17
    assert result1["skipped"] == 0
    assert result1["total"] == 17

    # DB 적재 확인
    count = db_session.query(AppRegistry).filter(AppRegistry.app_id.like("admin_%")).count()
    assert count == 17

    # 2회차: 중복 실행 시 모두 건너뜀 (created=0, skipped=17)
    result2 = bootstrap_system_apps(db_session)
    assert result2["created"] == 0
    assert result2["skipped"] == 17


def test_granular_permission_delegation_to_operations_group(db_session):
    """
    [검증 2] 운영 위임 모듈(알림 관리)에 특정 그룹('운영팀')을 allow_groups로 허가 시,
    사원(Lv.2)도 4단계 Allow-Wins 규칙에 따라 정상 접근 가능한지 검증
    """
    bootstrap_system_apps(db_session)

    alert_app = db_session.query(AppRegistry).filter(AppRegistry.app_id == "admin_alerts").first()
    assert alert_app is not None
    assert alert_app.min_read_rank == 4

    # 1. 일반 사원 (Lv.2, 그룹 없음) -> 기본 랭크(Lv.4) 미달로 차단
    normal_staff = _make_user("staff_lee", rank=2)
    assert can_access_app(normal_staff, alert_app, action="read") is False

    # 2. 관리자가 group-manage에서 alert_app에 '운영팀' 허용 그룹 배분
    alert_app.allow_groups = ["운영팀"]
    db_session.commit()
    db_session.refresh(alert_app)

    # 3. 운영팀 소속 사원 (Lv.2, primary_group='운영팀') -> Allow-Wins로 즉시 통과!
    ops_staff = _make_user("ops_kim", rank=2, primary_group="운영팀")
    assert can_access_app(ops_staff, alert_app, action="read") is True


def test_core_infrastructure_lock_for_low_rank(db_session):
    """
    [검증 3] 코어 인프라(admin_config)는 Lv.8 이상 관리자 및 root(Lv.9)만 통과하고
    일반 관리자(Lv.4)는 거부되는지 검증
    """
    bootstrap_system_apps(db_session)

    config_app = db_session.query(AppRegistry).filter(AppRegistry.app_id == "admin_config").first()
    assert config_app is not None
    assert config_app.min_read_rank == 8

    admin_lv4 = _make_user("admin_general", rank=4)
    admin_lv8 = _make_user("admin_sys", rank=8)
    root_user = _make_user("root_master", rank=9)

    # Lv.4 일반 관리자는 거부
    assert can_access_app(admin_lv4, config_app, action="read") is False

    # Lv.8 코어 관리자는 통과
    assert can_access_app(admin_lv8, config_app, action="read") is True

    # Lv.9 Root는 무조건 통과
    assert can_access_app(root_user, config_app, action="read") is True
