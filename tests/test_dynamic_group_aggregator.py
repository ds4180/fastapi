"""
============================================================================
[동적 타겟 그룹 실 데이터 연산 및 Redis 집합 갱신 검증 테스트 (tests/test_dynamic_group_aggregator.py)]
============================================================================
"""

import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User, UserProfile
from models.dayoff import DayOff
from models.dispatch import RouteMaster, RouteTimetable, Dispatch
from domain.v1.admin.group_router import calculate_and_refresh_dynamic_groups


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    UserProfile.__table__.create(engine)
    DayOff.__table__.create(engine)
    RouteMaster.__table__.create(engine)
    RouteTimetable.__table__.create(engine)
    Dispatch.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    today = datetime.now().date()

    # 1. 사용자 및 프로필 생성
    # 기사1 (id=101): 시내버스 소속, 오늘 승인된 휴무자
    u1 = User(id=101, username="driver_city1", email="c1@jeju.live", password="pw", real_name="김시내")
    p1 = UserProfile(user_id=101, primary_group="시내버스1팀", is_active=True)

    # 기사2 (id=102): 시내버스 소속, 오늘 근무자, 오늘 202번 배차 확정
    u2 = User(id=102, username="driver_city2", email="c2@jeju.live", password="pw", real_name="이시내")
    p2 = UserProfile(user_id=102, primary_group="시내버스2팀", is_active=True)

    # 기사3 (id=103): 시외버스 소속, 오늘 근무자, 오늘 101번 배차 확정
    u3 = User(id=103, username="driver_inter1", email="i1@jeju.live", password="pw", real_name="박시외")
    p3 = UserProfile(user_id=103, primary_group="시외버스급행팀", is_active=True)

    # 직원4 (id=201): 행정직, 오늘 근무자
    u4 = User(id=201, username="staff_admin", email="s1@jeju.live", password="pw", real_name="최행정")
    p4 = UserProfile(user_id=201, primary_group="운영관리팀", is_active=True)

    session.add_all([u1, p1, u2, p2, u3, p3, u4, p4])

    # 2. 휴무 데이터 등록: 기사1(101) 오늘 승인 휴무
    d1 = DayOff(id=1, user_id=101, date=today, type="연차", status="APPROVED", is_deleted=False)
    session.add(d1)

    # 3. 노선 및 시간표 등록
    rm_202 = RouteMaster(id=1, route_name="202", route_type="REGULAR", start_date=today, version="1.0")
    rm_101 = RouteMaster(id=2, route_name="101", route_type="REGULAR", start_date=today, version="1.0")
    session.add_all([rm_202, rm_101])
    session.flush()

    tt_202 = RouteTimetable(
        id=1, route_master_id=rm_202.id, route_name="202", seq=1,
        start_time="08:00", end_time="10:00", start_location="제주", end_location="서귀포", version="1.0"
    )
    tt_101 = RouteTimetable(
        id=2, route_master_id=rm_101.id, route_name="101", seq=1,
        start_time="09:00", end_time="11:00", start_location="제주", end_location="공항", version="1.0"
    )
    session.add_all([tt_202, tt_101])
    session.flush()

    # 4. 배차 등록: 기사2(102) -> 202번 배차 확정, 기사3(103) -> 101번 배차 확정
    dp_202 = Dispatch(id=1, target_date=today, timetable_id=tt_202.id, driver_name="이시내", status="CONFIRMED")
    dp_101 = Dispatch(id=2, target_date=today, timetable_id=tt_101.id, driver_name="박시외", status="CONFIRMED")
    session.add_all([dp_202, dp_101])

    session.commit()

    yield session
    session.close()


def test_dynamic_group_aggregation(db_session):
    """
    실 비즈니스 동적 그룹 연산(휴무자/근무자/시내외/노선배차)이 
    정확히 대상 user_id를 추출하여 Redis에 저장하는지 검증
    """
    # Redis 목(Mock) 객체
    mock_redis = MagicMock()
    redis_sets = {}
    redis_hashes = {}

    def mock_delete(key):
        if key in redis_sets:
            del redis_sets[key]

    def mock_sadd(key, *members):
        if key not in redis_sets:
            redis_sets[key] = set()
        for m in members:
            redis_sets[key].add(str(m))

    def mock_hset(name, key, value):
        if name not in redis_hashes:
            redis_hashes[name] = {}
        redis_hashes[name][key] = value

    mock_redis.delete.side_effect = mock_delete
    mock_redis.sadd.side_effect = mock_sadd
    mock_redis.hset.side_effect = mock_hset

    # 연산 실행
    results = calculate_and_refresh_dynamic_groups(db_session, mock_redis)

    # 1. 오늘 휴무자 검증 (기사1: 101)
    assert "group:data:today_dayoff" in redis_sets
    assert redis_sets["group:data:today_dayoff"] == {"101"}
    assert results["today_dayoff"] == 1

    # 2. 오늘 근무자 검증 (전체 101, 102, 103, 201 중 휴무자 101 제외 -> 102, 103, 201)
    assert "group:data:today_working" in redis_sets
    assert redis_sets["group:data:today_working"] == {"102", "103", "201"}
    assert results["today_working"] == 3

    # 3. 시내버스 운전자 검증 (기사1: 101, 기사2: 102)
    assert "group:data:bus_city" in redis_sets
    assert redis_sets["group:data:bus_city"] == {"101", "102"}
    assert results["bus_city"] == 2

    # 4. 시외버스 운전자 검증 (기사3: 103)
    assert "group:data:bus_intercity" in redis_sets
    assert redis_sets["group:data:bus_intercity"] == {"103"}
    assert results["bus_intercity"] == 1

    # 5. 오늘 202번 노선 운행 기사 검증 (기사2: 102)
    assert "group:data:dispatch_today_202" in redis_sets
    assert redis_sets["group:data:dispatch_today_202"] == {"102"}
    assert results["dispatch_today_202"] == 1

    # 6. 오늘 101번 노선 운행 기사 검증 (기사3: 103)
    assert "group:data:dispatch_today_101" in redis_sets
    assert redis_sets["group:data:dispatch_today_101"] == {"103"}
    assert results["dispatch_today_101"] == 1

    # 7. 메타데이터 생성 검증
    meta_hash = redis_hashes.get("group:metadata", {})
    assert "today_working" in meta_hash
    assert "today_dayoff" in meta_hash
    assert "bus_city" in meta_hash
    assert "bus_intercity" in meta_hash
    assert "dispatch_today_202" in meta_hash

    meta_obj = json.loads(meta_hash["today_working"])
    assert meta_obj["name"] == "today_working"
    assert meta_obj["type"] == "dynamic"


def test_system_group_service_direct_import_and_operations():
    """
    [신규 비즈니스 서비스 계층 분리 검증]
    - domain.system.group_service 직접 호출 시 정상 작동 및 집합 연산 검증
    """
    from domain.system.group_service import (
        combine_redis_groups,
        create_manual_redis_group,
        get_all_redis_groups,
        delete_redis_group,
        KEY_DATA,
        KEY_META
    )

    redis_sets = {}
    redis_hashes = {}

    mock_rd = MagicMock()
    mock_rd.delete.side_effect = lambda k: redis_sets.pop(k, None)
    mock_rd.sadd.side_effect = lambda k, *vals: redis_sets.setdefault(k, set()).update(vals)
    def _mock_hset(hk, f, v):
        if hk not in redis_hashes:
            redis_hashes[hk] = {}
        redis_hashes[hk][f] = v

    mock_rd.hset.side_effect = _mock_hset
    mock_rd.scard.side_effect = lambda k: len(redis_sets.get(k, set()))
    mock_rd.hgetall.side_effect = lambda hk: redis_hashes.get(hk, {})

    # 1. 수동 그룹 생성
    create_manual_redis_group("vip_drivers", [101, 102], mock_rd)
    assert redis_sets[f"{KEY_DATA}vip_drivers"] == {"101", "102"}

    # 2. 그룹 목록 조회
    groups = get_all_redis_groups(mock_rd)
    assert len(groups) == 1
    assert groups[0]["name"] == "vip_drivers"
    assert groups[0]["count"] == 2

    # 3. 그룹 삭제
    delete_redis_group("vip_drivers", mock_rd)
    mock_rd.hdel.assert_called_with(KEY_META, "vip_drivers")
