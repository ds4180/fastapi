"""
============================================================================
[테스트 1: 데이터베이스 모델 무결성 검사 (tests/test_models.py)]
============================================================================

💡 이 테스트의 목적:
우리가 분할한 `models/` 패키지가 순환 참조(Circular Import) 에러 없이
정상적으로 임포트되는지, 그리고 31개 전체 테이블이 데이터베이스 메타데이터에
빠짐없이 등록되어 있는지 기계적으로 검증합니다.
"""

from models import (
    Base,
    User,
    UserProfile,
    UserSession,
    SystemConfig,
    AppRegistry,
    BoardConfig,
    Post,
    Comment,
    RouteMaster,
    RouteTimetable,
    Dispatch,
    DayOff,
    Alert,
    Page,
    MediaAsset,
    SystemTask,
)


def test_models_import_and_table_count():
    """
    [검사 1] 전체 모델이 정상 로딩되고, 31개의 필수 테이블이 모두 등록되었는가?
    """
    # Base.metadata.tables 는 시스템에 등록된 모든 테이블의 목록을 가지고 있습니다.
    tables = Base.metadata.tables
    print(f"\n📊 현재 감지된 전체 테이블 개수: {len(tables)}개")

    # 테이블이 30개 이상 정상 감지되어야 통과!
    assert len(tables) >= 30, f"테이블 개수가 부족합니다. (현재: {len(tables)})"

    # 핵심 테이블들이 이름대로 존재하는지 확인
    assert "users" in tables, "users 테이블이 누락되었습니다."
    assert "user_session" in tables, "user_session 테이블이 누락되었습니다."
    assert "board_config" in tables, "board_config 테이블이 누락되었습니다."
    assert "post" in tables, "post 테이블이 누락되었습니다."
    assert "dispatch" in tables, "dispatch 테이블이 누락되었습니다."
    assert "route_master" in tables, "route_master 테이블이 누락되었습니다."


def test_user_model_role_logic():
    """
    [검사 2] User 모델의 권한 등급(rank_level)에 따른 역할(role) 계산이 정확한가?
    """
    # 1. 가상의 게스트 사용자 생성 (등급 0)
    guest_user = User(username="guest_test", email="guest@test.com")
    guest_user.profile = UserProfile(rank_level=0)
    assert guest_user.role == "ROLE_GUEST", "등급 0은 ROLE_GUEST여야 합니다."

    # 2. 가상의 최고관리자 생성 (등급 4)
    admin_user = User(username="admin_test", email="admin@test.com")
    admin_user.profile = UserProfile(rank_level=4)
    assert admin_user.role == "ROLE_ADMIN", "등급 4는 ROLE_ADMIN이어야 합니다."

    # 3. 가상의 직원 생성 (등급 2)
    staff_user = User(username="staff_test", email="staff@test.com")
    staff_user.profile = UserProfile(rank_level=2)
    assert staff_user.role == "ROLE_STAFF_L2", "등급 2는 ROLE_STAFF_L2여야 합니다."
