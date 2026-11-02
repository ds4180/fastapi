"""
============================================================================
[테스트 4: 코어 4단계 권한(인가) 엔진 무결성 검사 (tests/test_permission.py)]
============================================================================

💡 이 테스트의 목적:
`정책재정의.md`에 정의된 4단계 권한 판별 규칙(core/permission.py)이
모든 경우의 수에서 정확하게 작동하는지 기계적으로 검증합니다.

검증 순서:
1. root(랭킹 == 9) 인가? ➔ 무조건 읽기/쓰기 모두 통과
2. 앱의 deny 값에 부그룹/주그룹이 있는가? ➔ 있으면 무조건 차단 (Deny-Wins)
3. 앱의 allow 값에 부그룹/주그룹이 있는가? ➔ 있으면 읽기/쓰기 모두 통과 (Allow-Wins)
4. 앱의 읽기/쓰기 랭킹과 사용자 랭킹(0~9) 비교 (>, <, ==, >=, <=)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models import User, UserProfile, AppRegistry
from core.permission import evaluate_permission, can_access_app, compare_rank, extract_groups_for_action


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
    """테스트용 가상 사용자 생성 헬퍼"""
    u = User(username=username, email=f"{username}@jeju.live")
    u.profile = UserProfile(
        rank_level=rank,
        primary_group=primary_group,
        secondary_groups=secondary_groups or [],
    )
    return u


def test_step1_root_bypasses_everything():
    """
    [1단계 검사] root(랭킹 9)는 deny 그룹에 속해 있거나 요구 랭킹이 높아도 무조건 통과해야 한다.
    """
    root_user = _make_user("root_admin", rank=9, primary_group="외주", secondary_groups=["차단대상"])

    # deny_groups에 '외주'와 '차단대상'이 모두 들어 있어도 root(9)는 프리패스!
    assert evaluate_permission(
        user=root_user,
        action="write",
        min_read_rank=9,
        min_write_rank=9,
        allow_groups=[],
        deny_groups=["외주", "차단대상"],
    ) is True


def test_step2_deny_group_blocks_even_high_rank():
    """
    [2단계 검사] 앱의 deny 목록에 주그룹 또는 부그룹이 하나라도 포함되면,
    랭킹이 4(관리자)이거나 allow 그룹에 동시에 속해 있어도 무조건 차단되어야 한다.
    """
    # 랭킹은 4이고 주그룹은 '운수팀'(allow)이지만, 부그룹 중 '휴직자'(deny)가 있는 사용자
    user = _make_user("suspended_mgr", rank=4, primary_group="운수팀", secondary_groups=["배차담당", "휴직자"])

    assert evaluate_permission(
        user=user,
        action="read",
        min_read_rank=1,
        min_write_rank=2,
        allow_groups=["운수팀"],
        deny_groups=["휴직자"],
    ) is False

    assert evaluate_permission(
        user=user,
        action="write",
        min_read_rank=1,
        min_write_rank=2,
        allow_groups=["운수팀"],
        deny_groups=["휴직자"],
    ) is False


def test_step3_allow_group_grants_both_read_and_write():
    """
    [3단계 검사] 앱의 allow 목록에 주그룹 또는 부그룹이 속하면,
    사용자의 랭킹(1)이 앱의 쓰기 랭킹(4)보다 낮아도 읽기와 쓰기가 모두 가능해야 한다.
    """
    # 일반 사원(랭킹 1)이지만 부그룹에 '배차담당'이 있는 사용자
    staff = _make_user("driver_kim", rank=1, primary_group="운수팀", secondary_groups=["배차담당"])

    # 원래 쓰기 랭킹이 4인 앱이지만, '배차담당'이 allow에 있으므로 읽기/쓰기 모두 True!
    assert evaluate_permission(
        user=staff,
        action="read",
        min_read_rank=2,
        min_write_rank=4,
        allow_groups=["배차담당"],
        deny_groups=[],
    ) is True

    assert evaluate_permission(
        user=staff,
        action="write",
        min_read_rank=2,
        min_write_rank=4,
        allow_groups=["배차담당"],
        deny_groups=[],
    ) is True


def test_step4_rank_fallback_and_comparisons():
    """
    [4단계 검사] 그룹에 해당하지 않을 때는 앱의 읽기/쓰기 랭킹과 사용자 랭킹(0~9)을 비교한다.
    """
    normal_user = _make_user("normal_user", rank=2, primary_group="총무팀", secondary_groups=[])

    app = AppRegistry(
        app_id="notice_board",
        name="공지사항",
        min_read_rank=1,
        min_write_rank=3,
        allow_groups=["인사팀"],
        deny_groups=["외주"],
    )

    # 랭킹 2는 읽기(min_read_rank=1)는 가능하지만, 쓰기(min_write_rank=3)는 불가!
    assert can_access_app(normal_user, app, action="read") is True
    assert can_access_app(normal_user, app, action="write") is False

    # 크다(>), 작다(<), 같다(==) 연산자 검증
    assert compare_rank(3, 2, ">") is True
    assert compare_rank(2, 2, "==") is True
    assert compare_rank(1, 2, "<") is True


def test_extract_groups_for_action_utility():
    """
    [JSONB 추출기 검증]
    extract_groups_for_action 함수가 단순 리스트, 딕셔너리, 문자열, all 키를 완벽히 처리하는지 검증합니다.
    """
    # 1. 단순 리스트 모드 (하위 호환)
    assert extract_groups_for_action(["운수팀", "정비팀"], action="read") == {"운수팀", "정비팀"}
    assert extract_groups_for_action(["운수팀", "정비팀"], action="write") == {"운수팀", "정비팀"}

    # 2. 딕셔너리 액션 분리 모드
    dict_groups = {"read": ["운수팀"], "write": ["배차담당"], "all": ["비상대책위"]}
    assert extract_groups_for_action(dict_groups, action="read") == {"운수팀", "비상대책위"}
    assert extract_groups_for_action(dict_groups, action="write") == {"배차담당", "비상대책위"}
    assert extract_groups_for_action(dict_groups, action="delete") == {"비상대책위"}

    # 3. None 또는 빈 값
    assert extract_groups_for_action(None) == set()
    assert extract_groups_for_action([]) == set()
    assert extract_groups_for_action({}) == set()


def test_step3_action_dict_mode_allow():
    """
    [JSONB 세분화 허용 검증]
    allow_groups = {"read": ["운수팀"], "write": ["배차담당"]} 일 때:
    - 운수팀 사원(rank 1)은 읽기는 통과하나, 쓰기는 쓰기 랭킹(4)에 막혀 차단되어야 한다.
    - 배차담당 사원(rank 1)은 쓰기 allow에 등록되어 있으므로 쓰기 랭킹(4)보다 낮아도 쓰기가 통과되어야 한다.
    """
    driver = _make_user("driver_a", rank=1, primary_group="운수팀")
    dispatcher = _make_user("dispatcher_b", rank=1, primary_group="총무팀", secondary_groups=["배차담당"])
    executive = _make_user("executive_c", rank=5, primary_group="기획실")

    app_perms = {
        "min_read_rank": 3,
        "min_write_rank": 4,
        "allow_groups": {"read": ["운수팀"], "write": ["배차담당"]},
        "deny_groups": [],
    }

    # 운수팀 사원 (rank 1)
    assert evaluate_permission(user=driver, action="read", **app_perms) is True   # allow["read"]로 즉시 통과
    assert evaluate_permission(user=driver, action="write", **app_perms) is False  # allow["write"]에 없고 rank 1 < 4

    # 배차담당 사원 (rank 1)
    assert evaluate_permission(user=dispatcher, action="read", **app_perms) is False # allow["read"]에 없고 rank 1 < 3
    assert evaluate_permission(user=dispatcher, action="write", **app_perms) is True  # allow["write"]로 즉시 통과

    # 고위 임원 (rank 5) - 그룹 미지정이지만 4단계 랭킹(5 >= 3, 5 >= 4)으로 둘 다 통과
    assert evaluate_permission(user=executive, action="read", **app_perms) is True
    assert evaluate_permission(user=executive, action="write", **app_perms) is True


def test_step2_action_dict_mode_deny():
    """
    [JSONB 세분화 차단 검증]
    deny_groups = {"write": ["수습기사"]} 일 때:
    - 수습기사(rank 2)는 읽기(min_read_rank 1)는 정상 통과하지만, 쓰기(action="write")는 Deny-Wins로 즉시 차단되어야 한다.
    """
    apprentice = _make_user("apprentice_kim", rank=2, primary_group="운수팀", secondary_groups=["수습기사"])

    app_perms = {
        "min_read_rank": 1,
        "min_write_rank": 2,
        "allow_groups": [],
        "deny_groups": {"write": ["수습기사"]},
    }

    # 읽기는 deny_groups["write"]에 걸리지 않으므로 4단계 랭킹(2 >= 1)으로 통과!
    assert evaluate_permission(user=apprentice, action="read", **app_perms) is True

    # 쓰기는 deny_groups["write"]에 수습기사가 있으므로 랭킹(2 >= 2)과 무관하게 즉시 차단!
    assert evaluate_permission(user=apprentice, action="write", **app_perms) is False


def test_require_app_permission_guard(db_session):
    """
    [신규 1단계 가드 검증: require_app_permission]
    - 랭크 8 이상 요구 앱('admin_tasks')에 랭크 2 사원이 접근하면 AccessDeniedError 발생
    - 랭크 9(root) 또는 랭크 8 관리자는 정상 통과
    """
    import pytest
    from core.deps import require_app_permission
    from core.exceptions import AccessDeniedError

    # 가상 DB에 앱 등록
    app = AppRegistry(
        app_id="test_admin_tasks",
        name="태스크 관리",
        min_read_rank=8,
        min_write_rank=8,
        allow_groups=[],
        deny_groups=[]
    )
    db_session.add(app)
    db_session.commit()

    guard_read = require_app_permission("test_admin_tasks", action="read")

    # 1. 랭크 2 사원 접근 시 AccessDeniedError 발생
    low_rank_user = _make_user("staff_low", rank=2)
    with pytest.raises(AccessDeniedError):
        guard_read(current_user=low_rank_user, db=db_session)

    # 2. 랭크 8 관리자 접근 시 정상 통과
    admin_user = _make_user("admin_high", rank=8)
    passed_user = guard_read(current_user=admin_user, db=db_session)
    assert passed_user.username == "admin_high"


def test_extract_all_groups_from_spec():
    """
    [JSONB 듀얼 그룹 추출기 검증]
    - 리스트 및 딕셔너리 규격에서 'read', 'write' 키가 아닌 실제 그룹명만 정확히 추출하는지 검증
    """
    from domain.v1.admin.auth_group_router import extract_all_groups_from_spec

    # 1. 단순 리스트 모드
    spec_list = ["운수팀", "배차담당"]
    assert extract_all_groups_from_spec(spec_list) == {"운수팀", "배차담당"}

    # 2. 딕셔너리 모드
    spec_dict = {"read": ["운수1팀", "운수2팀"], "write": ["배차담당"], "all": ["기획실"]}
    assert extract_all_groups_from_spec(spec_dict) == {"운수1팀", "운수2팀", "배차담당", "기획실"}

    # 3. 빈 값 및 None 모드
    assert extract_all_groups_from_spec(None) == set()
    assert extract_all_groups_from_spec([]) == set()
    assert extract_all_groups_from_spec({}) == set()
