"""
[결근/휴무 정책 Append-Only 원장 및 사용 제한 검증 테스트 (tests/test_dayoff_policy_ledger.py)]
"""

from datetime import date, timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.effective import pick
from models.user import User, UserProfile
from models.system import SystemConfig
from models.dayoff import DayOff, DayOffPolicy
from domain.dayoff import dayoff_crud, dayoff_schema


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    SystemConfig.__table__.create(engine)
    DayOff.__table__.create(engine)
    DayOffPolicy.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    driver = User(id=1, username="driver1", password="pwd", email="driver1@test.com", real_name="김기사")
    driver_profile = UserProfile(user_id=1, rank_level=1, primary_group="운수1팀", is_active=True)
    office = User(id=2, username="office1", password="pwd", email="office1@test.com", real_name="이사무")
    office_profile = UserProfile(user_id=2, rank_level=3, primary_group="관리팀", is_active=True)

    legacy = SystemConfig(
        key="dayoff_policy",
        value={
            "classify_mode": "BOTH",
            "fcfs_groups": ["운전직", "운수1팀"],
            "fcfs_ranks": [1],
            "daily_quota": 3,
            "date_overrides": {"2026-11-25": 2},
        },
    )
    session.add_all([driver, driver_profile, office, office_profile, legacy])
    session.commit()

    yield session
    session.close()


def test_append_only_copy_and_month_coexistence(db_session):
    """[검증 1] Append-Only 추가 시 기존 값 전부 복사 + 적용일/정원만 변경 & 월별 정원 공존"""
    # 1. 초기 이관 확인
    p_nov = dayoff_crud.get_dayoff_policy(db_session, date(2026, 11, 20))
    assert p_nov["id"] == 1
    assert p_nov["daily_quota"] == 3
    assert p_nov["fcfs_groups"] == ["운전직", "운수1팀"]
    assert dayoff_crud.get_date_overrides(db_session) == {"2026-11-25": 2}

    # 2. 12월 1일부터 정원 5명 + etc 확장필드 추가 (effective_date, daily_quota, etc만 넘김)
    saved = dayoff_crud.save_dayoff_policy(
        db_session,
        {
            "effective_date": date(2026, 12, 1),
            "daily_quota": 5,
            "etc": {"notice": "12월 성수기 증원", "allow_weekend": True},
        },
    )
    assert saved["id"] == 2
    assert saved["effective_date"] == "2026-12-01"
    assert saved["daily_quota"] == 5
    # 나머지 필드 그대로 복사되었는지 확인
    assert saved["classify_mode"] == "BOTH"
    assert saved["fcfs_groups"] == ["운전직", "운수1팀"]
    assert saved["fcfs_ranks"] == [1]
    assert saved["etc"] == {"notice": "12월 성수기 증원", "allow_weekend": True}

    # 3. 11월과 12월 달력 정원 동시 공존 검증
    nov_status = dayoff_crud.get_monthly_quota_status(db_session, 2026, 11)
    dec_status = dayoff_crud.get_monthly_quota_status(db_session, 2026, 12)
    assert nov_status["days"]["2026-11-20"]["quota"] == 3
    assert nov_status["days"]["2026-11-25"]["quota"] == 2  # 예외 정원 유지
    assert dec_status["days"]["2026-12-05"]["quota"] == 5


def test_soft_delete_fallback(db_session):
    """[검증 2] 예약 삭제(소프트 삭제) 시 pick()이 직전 유효 행을 자동 선택"""
    r2 = dayoff_crud.save_dayoff_policy(
        db_session,
        {"effective_date": date(2026, 12, 1), "daily_quota": 5, "max_monthly_count": 2},
    )
    assert dayoff_crud.get_dayoff_policy(db_session, date(2026, 12, 10))["daily_quota"] == 5

    # r2 삭제 -> pick()이 자동으로 id=1(정원 3)로 복귀
    assert dayoff_crud.delete_dayoff_policy_row(db_session, r2["id"]) is True
    assert dayoff_crud.get_dayoff_policy(db_session, date(2026, 12, 10))["daily_quota"] == 3

    # 마지막 1건 삭제 시도 시 차단
    with pytest.raises(HTTPException) as exc:
        dayoff_crud.delete_dayoff_policy_row(db_session, 1)
    assert exc.value.status_code == 400


def test_monthly_count_and_max_days_per_request(db_session):
    """[검증 3] 월별 최대 사용 횟수 및 1회 최대 사용 일수 제한 동작"""
    dayoff_crud.save_dayoff_policy(
        db_session,
        {
            "effective_date": date(2026, 12, 1),
            "daily_quota": 5,
            "max_monthly_count": 1,
            "max_days_per_request": 2,
        },
    )

    # 1. 1회 3일 신청 -> max_days_per_request=2 초과로 차단
    with pytest.raises(HTTPException) as exc1:
        dayoff_crud.create_dayoff_list(
            db_session,
            dayoff_schema.DayOffCreate(
                type=dayoff_schema.DayOffType.ANNUAL,
                dates=[date(2026, 12, 2), date(2026, 12, 3), date(2026, 12, 4)],
            ),
            user_id=1,
        )
    assert exc1.value.status_code == 400

    # 2. 1회 2일 신청 -> 성공 (12월 사용 횟수 1/1 소진)
    cnt = dayoff_crud.create_dayoff_list(
        db_session,
        dayoff_schema.DayOffCreate(
            type=dayoff_schema.DayOffType.ANNUAL,
            dates=[date(2026, 12, 2), date(2026, 12, 3)],
        ),
        user_id=1,
    )
    assert cnt == 2

    # 3. 같은 12월에 2회차 신청 -> max_monthly_count=1 도달로 차단
    with pytest.raises(HTTPException) as exc2:
        dayoff_crud.create_dayoff_list(
            db_session,
            dayoff_schema.DayOffCreate(
                type=dayoff_schema.DayOffType.ANNUAL,
                dates=[date(2026, 12, 10)],
            ),
            user_id=1,
        )
    assert exc2.value.status_code == 400

    # 4. 2027년 1월 신청 -> 월이 달라 정상 허용
    cnt_jan = dayoff_crud.create_dayoff_list(
        db_session,
        dayoff_schema.DayOffCreate(
            type=dayoff_schema.DayOffType.ANNUAL,
            dates=[date(2027, 1, 5)],
        ),
        user_id=1,
    )
    assert cnt_jan == 1


def test_advance_window_min_max_days(db_session):
    """[검증 4] 결근계 사용 가능 날짜(D+X ~ D+Y) 최소·최대 범위 저장·복사·차단 검증"""
    today = date.today()

    # 잘못된 범위(max > 0 이고 max < min) 등록 시 400 차단
    with pytest.raises(HTTPException) as bad_exc:
        dayoff_crud.save_dayoff_policy(
            db_session,
            {
                "effective_date": today,
                "min_advance_days": 10,
                "max_advance_days": 5,
            },
        )
    assert bad_exc.value.status_code == 400

    # 오늘부터 D+2 ~ D+5 까지만 신청 가능하도록 설정
    saved = dayoff_crud.save_dayoff_policy(
        db_session,
        {
            "effective_date": today,
            "min_advance_days": 2,
            "max_advance_days": 5,
        },
    )
    assert saved["min_advance_days"] == 2
    assert saved["max_advance_days"] == 5

    # D+1 (최소일 D+2 이전) 신청 차단
    with pytest.raises(HTTPException) as min_exc:
        dayoff_crud.create_dayoff_list(
            db_session,
            dayoff_schema.DayOffCreate(
                type=dayoff_schema.DayOffType.ANNUAL,
                dates=[today + timedelta(days=1)],
            ),
            user_id=1,
        )
    assert min_exc.value.status_code == 400

    # D+6 (최대일 D+5 이후) 신청 차단
    with pytest.raises(HTTPException) as max_exc:
        dayoff_crud.create_dayoff_list(
            db_session,
            dayoff_schema.DayOffCreate(
                type=dayoff_schema.DayOffType.ANNUAL,
                dates=[today + timedelta(days=6)],
            ),
            user_id=1,
        )
    assert max_exc.value.status_code == 400

    # 경계값 D+2 ~ D+3 정상 허용
    ok_cnt = dayoff_crud.create_dayoff_list(
        db_session,
        dayoff_schema.DayOffCreate(
            type=dayoff_schema.DayOffType.ANNUAL,
            dates=[today + timedelta(days=2), today + timedelta(days=3)],
        ),
        user_id=1,
    )
    assert ok_cnt == 2

    # 이후 정원만 바꿔 Append-Only 등록해도 min/max_advance_days 값 자동 유지 확인
    copied = dayoff_crud.save_dayoff_policy(
        db_session,
        {
            "effective_date": today + timedelta(days=1),
            "daily_quota": 7,
        },
    )
    assert copied["min_advance_days"] == 2
    assert copied["max_advance_days"] == 5


def test_single_reserved_policy_and_date_override_separation(db_session):
    """[검증 5] 미래 예약 최대 1건 유지, 예약 중 오늘 저장 차단, 예외 정원 완전 분리"""
    today = date.today()
    future_1 = today + timedelta(days=5)
    future_2 = today + timedelta(days=10)

    # 1. 첫 미래 예약 등록
    r1 = dayoff_crud.save_dayoff_policy(
        db_session,
        {"effective_date": future_1, "daily_quota": 5},
    )
    assert dayoff_crud.get_reserved_dayoff_policy(db_session, today)["id"] == r1["id"]

    # 2. 예약이 이미 있을 때 오늘 적용 저장 시도 -> 409 차단
    with pytest.raises(HTTPException) as conflict_exc:
        dayoff_crud.save_dayoff_policy(
            db_session,
            {"effective_date": today, "daily_quota": 4},
        )
    assert conflict_exc.value.status_code == 409

    # 3. 미래 날짜로 다시 저장 시 기존 예약은 자동 소프트 삭제되고 새 레코드 1건만 유지
    r2 = dayoff_crud.save_dayoff_policy(
        db_session,
        {"effective_date": future_2, "daily_quota": 6},
    )
    assert r2["id"] != r1["id"]
    active_rows = dayoff_crud.get_all_dayoff_policies(db_session)
    future_rows = [r for r in active_rows if r.effective_date > today]
    assert len(future_rows) == 1
    assert future_rows[0].id == r2["id"]

    # 4. 특정일 예외 정원 수정 시 DayOffPolicy 행은 전혀 늘어나지 않고 독립 저장됨
    before_count = len(active_rows)
    ov_date = str(future_2 + timedelta(days=1))
    ov_res = dayoff_crud.update_date_overrides(db_session, [ov_date], 2)
    after_rows = dayoff_crud.get_all_dayoff_policies(db_session)
    assert len(after_rows) == before_count
    assert ov_res[ov_date] == 2
    assert dayoff_crud.get_date_overrides(db_session)[ov_date] == 2
