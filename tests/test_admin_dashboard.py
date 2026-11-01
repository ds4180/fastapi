"""
============================================================================
[코어 통합 관제탑 대시보드 요약 지표 검증 테스트 (tests/test_admin_dashboard.py)]
============================================================================
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User, UserProfile, UserSession
from models.system import SystemTask, AppRegistry
from models.board import BoardConfig, Post
from models.audit import AuditLog
from models.dayoff import DayOff
from models.miniapp import MiniappItem
from domain.v1.admin.admin_router import get_dashboard_summary


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    UserSession.__table__.create(engine)
    SystemTask.__table__.create(engine)
    AppRegistry.__table__.create(engine)
    BoardConfig.__table__.create(engine)
    Post.__table__.create(engine)
    AuditLog.__table__.create(engine)
    DayOff.__table__.create(engine)
    MiniappItem.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    today = datetime.now().date()
    now = datetime.now()

    # 1. 관리자 및 유저 생성
    admin = User(id=1, username="admin_master", email="admin@jeju.live", password="pw", real_name="총괄관리자")
    u2 = User(id=2, username="driver1", email="d1@jeju.live", password="pw", real_name="기사1")
    u3 = User(id=3, username="driver2", email="d2@jeju.live", password="pw", real_name="기사2")
    session.add_all([admin, u2, u3])

    p1 = UserProfile(user_id=1, rank_level=9, is_active=True)
    p2 = UserProfile(user_id=2, rank_level=2, is_active=True)
    p3 = UserProfile(user_id=3, rank_level=2, is_active=True)
    session.add_all([p1, p2, p3])

    # 2. 자율신경계 태스크: PENDING 2건, RUNNING 1건, FAILED 1건
    t1 = SystemTask(id=1, task_type="MEDIA_GC", status="PENDING", scheduled_at=now + timedelta(hours=1))
    t2 = SystemTask(id=2, task_type="THUMB_GEN", status="PENDING", scheduled_at=now + timedelta(minutes=10))
    t3 = SystemTask(id=3, task_type="BACKUP", status="RUNNING", started_at=now)
    t4 = SystemTask(id=4, task_type="PUSH_SYNC", status="FAILED", retry_count=3)
    session.add_all([t1, t2, t3, t4])

    # 3. 감사로그: 최근 24시간 내 SECURITY 1건, ERROR 1건, 정상 ACCESS 2건
    a1 = AuditLog(id=1, user_id=2, log_type="SECURITY", app_id="admin_panel", action="DENIED", title="접근 차단", created_at=now - timedelta(hours=2))
    a2 = AuditLog(id=2, user_id=1, log_type="ERROR", app_id="upload", action="FAIL", title="업로드 실패", created_at=now - timedelta(hours=5))
    a3 = AuditLog(id=3, user_id=1, log_type="ACCESS", app_id="login", action="LOGIN", title="로그인 성공", created_at=now - timedelta(hours=1))
    session.add_all([a1, a2, a3])

    # 4. 실시간 세션: ACTIVE 2건, EXPIRED 1건
    s1 = UserSession(id=1, user_id=1, session_key="k1", device_category="DESKTOP", status="ACTIVE")
    s2 = UserSession(id=2, user_id=2, session_key="k2", device_category="MOBILE", status="ACTIVE")
    s3 = UserSession(id=3, user_id=3, session_key="k3", device_category="MOBILE", status="EXPIRED")
    session.add_all([s1, s2, s3])

    # 5. 오늘 휴무 1건 (기사1: u2)
    d1 = DayOff(id=1, user_id=2, date=today, type="연차", status="APPROVED", is_deleted=False)
    session.add(d1)

    # 6. 미니앱 지시사항: 미확인(PENDING) 2건, 확인완료(CONFIRMED) 1건
    m1 = MiniappItem(id=1, receiver_id=2, category="INSTRUCTION", content="지시1", status="PENDING")
    m2 = MiniappItem(id=2, receiver_id=3, category="INSTRUCTION", content="지시2", status="PENDING")
    m3 = MiniappItem(id=3, receiver_id=2, category="INSTRUCTION", content="지시3", status="CONFIRMED")
    m4 = MiniappItem(id=4, receiver_id=3, category="NOTIFICATION", content="일반공지", status="PENDING")
    session.add_all([m1, m2, m3, m4])

    # 7. 기본 메타 카운트용
    b1 = BoardConfig(id=1, slug="notice", name="공지사항", is_active=True)
    post1 = Post(id=1, board_id=1, user_id=1, title="첫 공지", content="내용", content_json={})
    app1 = AppRegistry(app_id="board", name="게시판")
    session.add_all([b1, post1, app1])

    session.commit()

    yield session
    session.close()


def test_core_control_tower_dashboard_summary(db_session):
    """
    관제탑 대시보드가 4대 코어 지표(워커, 보안, 세션/근무, 지시사항 인지율)를 정확히 집계하는지 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    summary = get_dashboard_summary(db=db_session, admin=admin)

    # 1. 관리자명 확인
    assert summary["admin_name"] == "총괄관리자"

    # 2. 자율신경계 태스크 엔진 지표 검증
    task_stat = summary["task_engine"]
    assert task_stat["pending_count"] == 2
    assert task_stat["running_count"] == 1
    assert task_stat["failed_count"] == 1
    assert task_stat["is_healthy"] is False  # 실패 1건 존재하므로 False
    assert task_stat["next_scheduled_task"] is not None

    # 3. 통합 관제 & 보안 감시 지표 검증
    obs_stat = summary["observability"]
    assert obs_stat["security_breach_24h"] == 1
    assert obs_stat["error_log_24h"] == 1
    assert obs_stat["active_sessions"] == 2  # ACTIVE 2건

    # 4. 오늘 근무 및 휴무 비율 검증
    duty_stat = summary["duty_status"]
    assert duty_stat["dayoff_count"] == 1  # 휴무 1명
    assert duty_stat["active_user_count"] == 3  # 활성 3명
    assert duty_stat["working_count"] == 2  # 3 - 1 = 2명 근무

    # 5. 현장 지시사항 미확인 인지율 검증
    watchdog = summary["instruction_watchdog"]
    assert watchdog["unconfirmed_count"] == 2  # m1, m2 미확인

    # 6. 하위 호환 필드 검증
    assert summary["user_count"] == 3
    assert summary["board_count"] == 1
    assert summary["post_count"] == 1
    assert summary["app_count"] == 1
