"""
============================================================================
[전역 통합 알림 단일 디스패처 검증 테스트 (tests/test_notify.py)]
============================================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models.user import User, UserProfile
from models.miniapp import MiniappItem
from models.alert import Alert
from core.notify import notify, safe_notify, resolve_target_user_ids


@pytest.fixture
def db_session():
    """인메모리 SQLite 격리 테스트 세션"""
    engine = create_engine("sqlite:///:memory:")
    # 필요한 테이블들 생성
    User.__table__.create(engine)
    MiniappItem.__table__.create(engine)
    Alert.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # 테스트 유저 생성
    u1 = User(id=1, username="admin", password="p", email="a@t.com")
    u2 = User(id=2, username="driver_kim", password="p", email="k@t.com")
    u3 = User(id=3, username="driver_lee", password="p", email="l@t.com")
    session.add_all([u1, u2, u3])
    session.commit()

    yield session
    session.close()


def test_core_notify_broadcast(db_session):
    """
    [검증 1] 대상 미지정 ➔ 전사 공지(receiver_id is None) 단일 레코드 생성 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    items = notify(
        db=db_session,
        category="NOTIFICATION",
        title="[전사] 서버 긴급 점검 안내",
        message="오늘 밤 11시부터 10분간 점검이 있습니다.",
        sender=admin,
        level=1
    )

    assert len(items) == 1
    assert items[0].receiver_id is None
    assert items[0].sender_id == 1
    assert items[0].category == "NOTIFICATION"
    assert items[0].status == "PENDING"


def test_core_notify_target_users(db_session):
    """
    [검증 2] 특정 사원 다중 타겟팅 ➔ 각 사원별 1:1 인박스 레코드 생성 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    items = notify(
        db=db_session,
        category="INSTRUCTION",
        title="[배차 확정] 내일 노선 배정",
        message="101번 버스로 배정되었습니다.",
        sender=admin,
        target_user_ids=[2, 3],
        level=2,
        link="/v1/dispatch/my"
    )

    assert len(items) == 2
    rec_ids = {it.receiver_id for it in items}
    assert rec_ids == {2, 3}
    for it in items:
        assert it.sender_id == 1
        assert it.category == "INSTRUCTION"
        assert it.link == "/v1/dispatch/my"


def test_core_notify_level_and_modal_sync(db_session):
    """
    [검증 3] Level 4 경보 발령 시 ➔ 미니앱 적재 + Alert 모달 레코드 자동 동기화 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    items = notify(
        db=db_session,
        category="NOTIFICATION",
        title="[보안 경보] 비정상 다중 접속 감지",
        message="보안 정책 위반이 감지되어 점검을 실시합니다.",
        sender=admin,
        target_user_ids=[2],
        level=4
    )

    assert len(items) == 1
    # Alert 테이블에도 모달 레코드가 생성되었는가?
    alerts = db_session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].level == 4
    assert alerts[0].position == "modal"
    assert alerts[0].style == "warning"


def test_safe_notify_fallback(db_session):
    """
    [검증 4] 잘못된 인자 전달 시 safe_notify가 예외를 삼키고 빈 리스트를 안전 반환하는가?
    """
    # None db 세션을 강제로 넘겨도 프로세스가 죽지 않아야 함
    res = safe_notify(
        db=None,  # type: ignore
        message="테스트 메시지"
    )
    assert res == []
