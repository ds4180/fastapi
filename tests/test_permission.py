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

from models import User, UserProfile, AppRegistry
from core.permission import evaluate_permission, can_access_app, compare_rank


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
