"""
============================================================================
[타겟 그룹 연동 알림 및 미니앱 분류 피드 적재 테스트 (tests/test_target_group_alert.py)]
============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from models.base import Base
from models.user import User, UserProfile
from models.alert import Alert
from models.miniapp import MiniappItem
from domain.alert import alert_crud, alert_schema


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    MiniappItem.__table__.create(engine)
    Alert.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 테스트 유저 생성 (관리자, 대상 기사1, 대상 기사2, 비대상 일반인)
    admin = User(id=1, username="admin", email="admin@jeju.live", password="pw", real_name="관리자")
    driver1 = User(id=101, username="driver1", email="d1@jeju.live", password="pw", real_name="202번기사1")
    driver2 = User(id=102, username="driver2", email="d2@jeju.live", password="pw", real_name="202번기사2")
    other_user = User(id=999, username="other", email="other@jeju.live", password="pw", real_name="일반직원")

    session.add_all([admin, driver1, driver2, other_user])
    session.commit()

    yield session
    session.close()


def test_create_alert_with_target_group(db_session):
    import asyncio
    asyncio.run(_async_test_create_alert_with_target_group(db_session))


async def _async_test_create_alert_with_target_group(db_session):
    """
    Redis 타겟 그룹(202번_오전_운행기사)을 지정하여 알림을 생성할 때:
    1. Alert 레코드에 target_group과 category가 보존되는지 검증
    2. core.notify를 통해 Redis 그룹 멤버(101, 102)에게 MiniappItem이 INSTRUCTION 분류로 생성되는지 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()
    driver1 = db_session.query(User).filter_by(id=101).first()
    other = db_session.query(User).filter_by(id=999).first()

    # 가짜 Redis 목(Mock) 객체
    mock_redis = MagicMock()
    # 202번_오전_운행기사 그룹의 멤버로 101, 102 반환
    mock_redis.smembers.return_value = {"101", "102"}
    mock_redis.sismember.side_effect = lambda key, val: val in ("101", "102")

    alert_in = alert_schema.AlertCreate(
        message="202번 노선 일부 도로 결빙 주의 지시",
        level=3,
        style="warning",
        position="modal",
        category="INSTRUCTION",
        target_group="202번_오전_운행기사"
    )

    bg_tasks = MagicMock()

    with patch("redis_config.rd", mock_redis), patch("domain.alert.alert_crud.rd", mock_redis, create=True):
        db_alert = await alert_crud.create_alert(
            db=db_session,
            alert_create=alert_in,
            user=admin,
            background_tasks=bg_tasks
        )

        # 1. Alert 테이블 검증
        assert db_alert.id is not None
        assert db_alert.target_group == "202번_오전_운행기사"
        assert db_alert.category == "INSTRUCTION"

        # 2. 미니앱 DB에 101, 102 사원 인박스 아이템 적재 검증
        items = db_session.query(MiniappItem).all()
        assert len(items) == 2
        receiver_ids = {item.receiver_id for item in items}
        assert receiver_ids == {101, 102}
        for item in items:
            assert item.category == "INSTRUCTION"
            assert "202번" in item.content

        # 3. get_active_alerts 화면 노출 검증 (101번 기사에게는 노출, 999번 일반인에게는 제외)
        active_for_driver = alert_crud.get_active_alerts(db_session, user=driver1)
        assert len(active_for_driver) == 1
        assert active_for_driver[0].id == db_alert.id

        active_for_other = alert_crud.get_active_alerts(db_session, user=other)
        assert len(active_for_other) == 0
