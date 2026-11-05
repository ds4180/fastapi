"""
============================================================================
[백엔드 코어 4단계 권한(인가) 판별 엔진 (core/permission.py)]
============================================================================

💡 이 파일의 역할:
FastAPI의 HTTP 요청(Request/Cookie/HTTPException)과 완전히 분리된
'순수 권한 계산 비즈니스 서비스 모듈'입니다. (`정책재정의.md` 표준 100% 구현)

🌟 핵심 설계 원칙 (`정책재정의.md`):
1. 권한 랭킹은 0~9까지 존재하며, 9는 시스템 최고 절대 권한인 `root`입니다.
2. 주그룹(primary_group)은 최대 1개(선택), 부그룹(secondary_groups)은 1개 이상 복수(선택) 가능합니다.
3. 그룹은 항상 권한 랭킹보다 우선하며, 권한 판별은 반드시 아래 [1 ➔ 2 ➔ 3 ➔ 4단계] 순서를 따릅니다:
   - [1단계] root(랭킹 == 9) 인가? ➔ YES면 무조건 허용 (읽기/쓰기 모두 가능)
   - [2단계] 앱의 deny 목록(단순 리스트 또는 {"read": [...], "write": [...]})에 사용자의 부그룹 또는 주그룹이 있는가? ➔ YES면 무조건 차단 (Deny-Wins)
   - [3단계] 앱의 allow 목록(단순 리스트 또는 {"read": [...], "write": [...]})에 사용자의 부그룹 또는 주그룹이 있는가? ➔ YES면 무조건 허용 (Allow-Wins)
   - [4단계] 앱의 읽기/쓰기 랭킹과 사용자의 랭킹(0~9)을 비교(>=, >, <, <=, ==)하여 최종 결정
"""

from typing import Optional, Iterable, Any
from models import User

# 📌 시스템 최고 절대 권한(root) 랭킹 상수
ROOT_RANK = 9


def get_user_rank(user: Optional[User]) -> int:
    """
    사용자 객체에서 현재 권한 랭킹(0~9)을 안전하게 추출합니다.
    비로그인(None) 상태이면 항상 0(GUEST)을 반환합니다.
    """
    if not user:
        return 0
    r = user.rank() if callable(getattr(user, "rank", None)) else getattr(user, "rank", 0)
    return int(r) if r is not None else 0


def get_user_groups(user: Optional[User]) -> set[str]:
    """
    사용자의 주그룹(최대 1개)과 부그룹(1개 이상 리스트)을 모두 합쳐
    고속 교집합 연산이 가능한 파이썬 집합(set)으로 반환합니다.
    """
    if not user:
        return set()
    if callable(getattr(user, "all_groups", None)):
        return user.all_groups()

    groups: set[str] = set()
    primary = getattr(user, "primary_group", None)
    if primary:
        groups.add(primary)
    secondaries = getattr(user, "secondary_groups", None) or []
    for g in secondaries:
        if g:
            groups.add(g)
    return groups


def compare_rank(user_rank: int, target_rank: int, op: str = ">=") -> bool:
    """
    [랭킹 비교 연산기]
    0~9까지의 숫자 랭킹에 대해 크다(>), 작다(<), 같다(==), 이상(>=), 이하(<=) 비교를 수행합니다.
    """
    if op == ">=":
        return user_rank >= target_rank
    if op == ">":
        return user_rank > target_rank
    if op == "==":
        return user_rank == target_rank
    if op == "<=":
        return user_rank <= target_rank
    if op == "<":
        return user_rank < target_rank
    raise ValueError(f"지원하지 않는 랭킹 비교 연산자입니다: {op} (허용: '>=', '>', '==', '<=', '<')")


def extract_groups_for_action(group_data: Any, action: str = "read") -> set[str]:
    """
    [JSONB 듀얼 모드 그룹 추출기]
    allow_groups 및 deny_groups의 두 가지 규격을 유연하게 처리합니다:
    1. 단순 리스트/이터러블 모드: ["운수팀", "배차담당"]
       - 읽기/쓰기 구분 없이 모든 action에 공통 적용됩니다.
    2. 액션별 분리 딕셔너리 모드: {"read": ["운수팀"], "write": ["배차담당"], "all": ["기획실"]}
       - 요청된 action 키에 해당하는 그룹 목록과 "all" 키의 그룹 목록을 합쳐서 반환합니다.
    """
    if not group_data:
        return set()

    # 딕셔너리 형태인 경우 (액션별 분리 모드)
    if isinstance(group_data, dict):
        result: set[str] = set()
        # 요청된 특정 action(예: 'read' 또는 'write')에 지정된 그룹
        specific_groups = group_data.get(action)
        if isinstance(specific_groups, (list, set, tuple)):
            for g in specific_groups:
                if g:
                    result.add(str(g))
        elif isinstance(specific_groups, str) and specific_groups:
            result.add(specific_groups)

        # 전체 공통 적용 키('all')가 있다면 합집합 처리
        all_groups = group_data.get("all")
        if isinstance(all_groups, (list, set, tuple)):
            for g in all_groups:
                if g:
                    result.add(str(g))
        elif isinstance(all_groups, str) and all_groups:
            result.add(all_groups)

        return result

    # 단순 리스트/문자열/셋 형태인 경우 (하위 호환 마스터 모드)
    if isinstance(group_data, (list, set, tuple)):
        return {str(g) for g in group_data if g}
    if isinstance(group_data, str) and group_data:
        return {group_data}

    return set()


def evaluate_permission(
    user: Optional[User],
    action: str = "read",
    min_read_rank: int = 0,
    min_write_rank: int = 2,
    allow_groups: Optional[Any] = None,
    deny_groups: Optional[Any] = None,
    op: str = ">=",
) -> bool:
    """
    [`정책재정의.md` 4단계 권한 처리 핵심 엔진 (JSONB 듀얼 규격 지원)]

    1단계: root(랭킹 == 9) 인가? ➔ 무조건 True (읽기/쓰기 모두 가능)
    2단계: deny 목록(action 대응 또는 전체)에 사용자의 부그룹 또는 주그룹이 있는가? ➔ 있으면 무조건 False (차단)
    3단계: allow 목록(action 대응 또는 전체)에 사용자의 부그룹 또는 주그룹이 있는가? ➔ 있으면 무조건 True (허용)
    4단계: 앱의 읽기(min_read_rank) 또는 쓰기(min_write_rank) 랭킹과 사용자 랭킹(0~9) 비교
    """
    user_rank = get_user_rank(user)

    # ------------------------------------------------------------------------
    # [1단계] root(랭킹 == 9) 인가?
    # ------------------------------------------------------------------------
    if user_rank == ROOT_RANK:
        return True

    user_groups = get_user_groups(user)

    # ------------------------------------------------------------------------
    # [2단계] 앱의 deny 값에 부그룹이나 주그룹이 있는가? (Deny-Wins)
    #         단순 리스트 모드 및 {"read": [...], "write": [...]} 액션별 모드 지원
    # ------------------------------------------------------------------------
    effective_deny = extract_groups_for_action(deny_groups, action=action)
    if user_groups & effective_deny:
        return False

    # ------------------------------------------------------------------------
    # [3단계] 앱의 allow 값에 부그룹이나 주그룹이 있는가? (Allow-Wins)
    #         단순 리스트 모드 및 {"read": [...], "write": [...]} 액션별 모드 지원
    # ------------------------------------------------------------------------
    effective_allow = extract_groups_for_action(allow_groups, action=action)
    if user_groups & effective_allow:
        return True

    # ------------------------------------------------------------------------
    # [4단계] 앱의 읽기/쓰기 랭킹과 사용자의 랭킹(0~9) 비교 (기본값 Fallback)
    # ------------------------------------------------------------------------
    required_rank = min_write_rank if action == "write" else min_read_rank
    return compare_rank(user_rank, required_rank, op=op)


def can_access_app(user: Optional[User], app_obj: Any, action: str = "read", op: str = ">=") -> bool:
    """
    [AppRegistry 객체 기반 권한 판별 헬퍼 (킬 스위치 연동)]
    DB에서 조회한 AppRegistry 인스턴스를 넘기면 해당 앱의 활성화 여부(is_active) 및
    보안 설정(allow_groups, deny_groups, min_read_rank, min_write_rank)을 읽어
    4단계 규칙으로 읽기/쓰기 가능 여부를 즉시 반환합니다.
    """
    if not app_obj:
        return False

    # 🚨 [앱 킬 스위치]: 앱이 비활성화(is_active=False)된 경우 root(9)를 제외하고 즉시 차단
    if getattr(app_obj, "is_active", True) is False and get_user_rank(user) != ROOT_RANK:
        return False

    return evaluate_permission(
        user=user,
        action=action,
        min_read_rank=getattr(app_obj, "min_read_rank", 0) or 0,
        min_write_rank=getattr(app_obj, "min_write_rank", 2) or 0,
        allow_groups=getattr(app_obj, "allow_groups", None) or [],
        deny_groups=getattr(app_obj, "deny_groups", None) or [],
        op=op,
    )


def can_access_board(user: Optional[User], board_obj: Any, action: str = "read", op: str = ">=") -> bool:
    """
    [BoardConfig 객체 기반 4단계 권한 판별 헬퍼]
    1. root(9) 무조건 통과
    2. deny_groups 포함 시 즉시 차단
    3. allow_groups 포함 시 즉시 통과
    4. min_read_rank / min_write_rank 비교
    """
    if not board_obj:
        return False

    return evaluate_permission(
        user=user,
        action=action,
        min_read_rank=getattr(board_obj, "min_read_rank", 0) or 0,
        min_write_rank=getattr(board_obj, "min_write_rank", 2) or 0,
        allow_groups=getattr(board_obj, "allow_groups", None) or [],
        deny_groups=getattr(board_obj, "deny_groups", None) or [],
        op=op,
    )


def can_access_page(user: Optional[User], page_obj: Any, action: str = "read", op: str = ">=") -> bool:
    """
    [Page 객체 기반 4단계 권한 판별 헬퍼]
    1. root(9) 무조건 통과
    2. deny_groups 포함 시 즉시 차단
    3. allow_groups 포함 시 즉시 통과
    4. min_rank (열람 요구 등급) 비교
    """
    if not page_obj:
        return False

    return evaluate_permission(
        user=user,
        action=action,
        min_read_rank=getattr(page_obj, "min_rank", 0) or 0,
        min_write_rank=9,
        allow_groups=getattr(page_obj, "allow_groups", None) or [],
        deny_groups=getattr(page_obj, "deny_groups", None) or [],
        op=op,
    )

