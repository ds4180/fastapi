"""
============================================================================
[지시사항 양방향 수신 확인(Acknowledgement) 루프 검증 테스트 (tests/test_instruction_acknowledgement.py)]
============================================================================
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User, UserProfile
from models.alert import Alert
from models.miniapp import MiniappItem, MiniappRead
from core.notify import notify
from domain.v1.miniapp.miniapp_crud import update_miniapp_item
from domain.v1.miniapp.miniapp_schema import MiniappItemUpdate
from domain.alert.alert_crud import get_alert_acknowledgements


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    Alert.__table__.create(engine)
    MiniappItem.__table__.create(engine)
    MiniappRead.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. 사용자 생성: 관리자, 기사1, 기사2
    admin = User(id=1, username="admin_master", email="admin@jeju.live", password="pw", real_name="관리자")
    driver1 = User(id=101, username="driver101", email="d101@jeju.live", password="pw", real_name="김기사", phone="010-1111-2222")
    driver2 = User(id=102, username="driver102", email="d102@jeju.live", password="pw", real_name="이기사", phone="010-3333-4444")
    session.add_all([admin, driver1, driver2])

    p_admin = UserProfile(user_id=1, rank_level=9, is_active=True)
    p_d1 = UserProfile(user_id=101, rank_level=2, is_active=True)
    p_d2 = UserProfile(user_id=102, rank_level=2, is_active=True)
    session.add_all([p_admin, p_d1, p_d2])

    session.commit()

    yield session
    session.close()


def test_instruction_two_way_acknowledgement_flow(db_session):
    """
    지시사항 발송 -> 기사님 확인 완료 -> 관리자 수신 확인 현황 통계 집계 전체 플로우 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    # 1. Alert 생성
    alert = Alert(
        message="202번 노선 우회 운행 긴급 지시",
        level=3,
        style="warning",
        position="modal",
        category="INSTRUCTION",
        target_group="dispatch_today_202",
        create_date=datetime.now(),
        user_id=admin.id
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    # 2. core.notify를 통해 기사1(101)과 기사2(102)에게 지시사항 일괄 발송
    created_items = notify(
        db=db_session,
        category="INSTRUCTION",
        title="[지시] 긴급 우회 운행",
        message=alert.message,
        sender=admin,
        target_user_ids=[101, 102],
        level=3,
        extra_payload={"alert_id": alert.id, "target_group": "dispatch_today_202"}
    )
    db_session.commit()

    assert len(created_items) == 2
    for item in created_items:
        assert item.status == "PENDING"
        assert item.category == "INSTRUCTION"
        assert item.extra_payload.get("alert_id") == alert.id

    # 3. 발송 직후 수신 현황 조회 (아직 아무도 확인하지 않음)
    initial_stats = get_alert_acknowledgements(db_session, alert.id)
    assert initial_stats["total_count"] == 2
    assert initial_stats["confirmed_count"] == 0
    assert initial_stats["pending_count"] == 2
    assert initial_stats["confirm_rate"] == 0.0
    assert len(initial_stats["pending_users"]) == 2

    # 4. 기사1(101)이 모바일에서 [확인 완료] 클릭 (status -> CONFIRMED)
    d1_item = db_session.query(MiniappItem).filter(
        MiniappItem.receiver_id == 101,
        MiniappItem.category == "INSTRUCTION"
    ).first()

    updated = update_miniapp_item(
        db=db_session,
        item_id=d1_item.id,
        user_id=101,
        item_update=MiniappItemUpdate(status="CONFIRMED")
    )
    assert updated is not None
    assert updated.status == "CONFIRMED"
    # extra_payload에 confirmed_at이 자동 기록되었는지 검증
    assert "confirmed_at" in updated.extra_payload

    # 5. 관리자가 수신 확인 현황 재조회
    updated_stats = get_alert_acknowledgements(db_session, alert.id)
    assert updated_stats["total_count"] == 2
    assert updated_stats["confirmed_count"] == 1  # 기사1 확인 완료
    assert updated_stats["pending_count"] == 1    # 기사2 아직 미확인
    assert updated_stats["confirm_rate"] == 50.0  # 50% 확인율

    # 확인 완료자 명단 검증
    assert len(updated_stats["confirmed_users"]) == 1
    assert updated_stats["confirmed_users"][0]["user_id"] == 101
    assert updated_stats["confirmed_users"][0]["real_name"] == "김기사"
    assert updated_stats["confirmed_users"][0]["confirmed_at"] is not None

    # 미확인자 명단 검증
    assert len(updated_stats["pending_users"]) == 1
    assert updated_stats["pending_users"][0]["user_id"] == 102
    assert updated_stats["pending_users"][0]["real_name"] == "이기사"
    assert updated_stats["pending_users"][0]["phone"] == "010-3333-4444"
