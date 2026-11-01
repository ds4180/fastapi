"""
============================================================================
[미니앱 단일 텍스트 통합 엔진 검증 테스트 (tests/test_miniapp.py)]
============================================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models.user import User, UserProfile
from models.miniapp import MiniappItem
from domain.v1.miniapp import miniapp_crud, miniapp_schema


@pytest.fixture
def db_session():
    """인메모리 SQLite 격리 테스트 세션"""
    engine = create_engine("sqlite:///:memory:")
    # 필요한 테이블들 생성 (User 및 MiniappItem)
    User.__table__.create(engine)
    MiniappItem.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # 테스트용 사용자 생성 (1: 관리자, 2: 일반 사원)
    admin = User(id=1, username="admin_user", password="pwd", email="admin@test.com")
    staff = User(id=2, username="staff_user", password="pwd", email="staff@test.com")
    session.add_all([admin, staff])
    session.commit()

    yield session
    session.close()


def test_miniapp_relationship_memo(db_session):
    """
    [검증 1] 보내는 사람 == 받는 사람 ➔ 메모 (MEMO) 자동 판별 및 뱃지 계산
    """
    staff = db_session.query(User).filter_by(id=2).first()

    # 1. 사원이 본인에게 메모 등록 (receiver_id 지정 안 함)
    item_in = miniapp_schema.MiniappItemCreate(
        content="내일 아침 차량 점검하기",
        category="MEMO"
    )
    memo = miniapp_crud.create_miniapp_item(db_session, sender=staff, item_in=item_in)

    assert memo.id is not None
    assert memo.sender_id == 2
    assert memo.receiver_id == 2
    assert memo.category == "MEMO"
    assert memo.status == "PENDING"

    # 2. 뱃지 카운트 확인
    counts = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert counts["MEMO"] == 1
    assert counts["TOTAL"] == 1

    # 3. 메모 완료(COMPLETED) 처리 시 뱃지 차감 확인
    update_in = miniapp_schema.MiniappItemUpdate(status="COMPLETED")
    miniapp_crud.update_miniapp_item(db_session, item_id=memo.id, user_id=2, item_update=update_in)

    counts_after = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert counts_after["MEMO"] == 0
    assert counts_after["TOTAL"] == 0


def test_miniapp_relationship_instruction_and_status_cycle(db_session):
    """
    [검증 2] 상사 ➔ 사원 + 상태값 부여 ➔ 지시사항 (INSTRUCTION) 업무 라이프사이클
    """
    admin = db_session.query(User).filter_by(id=1).first()

    # 1. 관리자가 사원(id=2)에게 업무 지시 발령
    item_in = miniapp_schema.MiniappItemCreate(
        receiver_id=2,
        category="INSTRUCTION",
        title="긴급 배차 노선 확인 요망",
        content="101번 버스 대체 기사 투입 완료 바랍니다.",
        link="/v1/dispatch"
    )
    inst = miniapp_crud.create_miniapp_item(db_session, sender=admin, item_in=item_in)

    assert inst.sender_id == 1
    assert inst.receiver_id == 2
    assert inst.category == "INSTRUCTION"
    assert inst.status == "PENDING"

    # 2. 사원(id=2) 입장에서 지시사항 뱃지 증가 확인
    staff_counts = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert staff_counts["INSTRUCTION"] == 1
    assert staff_counts["TOTAL"] == 1

    # 3. 사원이 업무 진행(ONGOING)으로 상태 변경 -> 여전히 미완료이므로 뱃지 1 유지
    miniapp_crud.update_miniapp_item(
        db_session, item_id=inst.id, user_id=2,
        item_update=miniapp_schema.MiniappItemUpdate(status="ONGOING")
    )
    counts_ongoing = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert counts_ongoing["INSTRUCTION"] == 1

    # 4. 사원이 업무 완료(COMPLETED) 처리 -> 뱃지 0으로 즉시 소멸
    miniapp_crud.update_miniapp_item(
        db_session, item_id=inst.id, user_id=2,
        item_update=miniapp_schema.MiniappItemUpdate(status="COMPLETED")
    )
    counts_done = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert counts_done["INSTRUCTION"] == 0
    assert counts_done["TOTAL"] == 0


def test_miniapp_relationship_broadcast_notification(db_session):
    """
    [검증 3] 수신자 NULL ➔ 전사 공지 (NOTIFICATION) 사원 전체 자동 노출 검증
    """
    admin = db_session.query(User).filter_by(id=1).first()

    # 1. 전사 공지 레코드 생성 (receiver_id is None)
    noti = MiniappItem(
        sender_id=admin.id,
        receiver_id=None,
        category="NOTIFICATION",
        title="[전사공지] 정기 서버 점검 안내",
        content="오늘 밤 23시부터 10분간 점검이 있습니다.",
        status="PENDING"
    )
    db_session.add(noti)
    db_session.commit()

    # 2. 사원(id=2)의 뱃지 카운트에 전사 알림이 1개 잡히는가?
    counts = miniapp_crud.get_user_miniapp_counts(db_session, user_id=2)
    assert counts["NOTIFICATION"] == 1
    assert counts["TOTAL"] == 1

    # 3. 사원의 미니앱 피드 목록에 전사 알림이 정확히 조회되는가?
    items = miniapp_crud.get_user_miniapp_items(db_session, user_id=2)
    assert len(items) == 1
    assert items[0].title == "[전사공지] 정기 서버 점검 안내"
