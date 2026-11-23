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

# 📌 부그룹(allow_groups) 전용 앱 잠금 구간 (사용자 직접 부여 비권장)
GROUP_ONLY_RANKS = (6, 7)

# 📌 전역 권한 랭킹(0~9) 표준 Role 매핑 (보안_권한_랭크_표준.md SSOT)
RANK_ROLE_MAP = {
    0: "ROLE_GUEST",           # 비로그인 / 손님 / 미승인
    1: "ROLE_USER",            # 일반 정회원
    2: "ROLE_DRIVER",          # 운전원 (승무직)
    3: "ROLE_STAFF",           # 현장직·사무 내근직 (주임/대리)
    4: "ROLE_MANAGER",         # 사무 내근직 (과장/차장/부장)
    5: "ROLE_EXECUTIVE",       # 사무 내근직 (임원)
    6: "ROLE_GROUP_ONLY_L1",   # 특수 잠금 1 (부그룹 전용)
    7: "ROLE_GROUP_ONLY_L2",   # 특수 잠금 2 (고보안 부그룹 전용)
    8: "ROLE_CORE",            # 코어마스터 (시스템 관리자)
    9: "ROLE_ROOT",            # 최고 관리자 (Root)
}


def get_role_name(rank_level: int) -> str:
    """정수형 랭킹(0~9)에 대응하는 표준 Role 문자열 반환"""
    return RANK_ROLE_MAP.get(int(rank_level), f"ROLE_CUSTOM_L{int(rank_level)}")


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


# 📌 서비스앱 권한 정책 상수 (추상화 규격)
SERVICE_READ_POLICIES = ("inherit", "authenticated", "custom")
SERVICE_WRITE_POLICIES = ("inherit_read", "inherit_write", "authenticated", "custom")


def _check_host_read(user: Optional[User], host_obj: Any) -> bool:
    """호스트 앱(BoardConfig, Page, AppRegistry 등)의 읽기 권한 평가"""
    if not host_obj:
        return True
    min_read = getattr(host_obj, "min_read_rank", None)
    if min_read is None:
        min_read = getattr(host_obj, "min_rank", 0)
    return evaluate_permission(
        user=user,
        action="read",
        min_read_rank=min_read or 0,
        min_write_rank=getattr(host_obj, "min_write_rank", 2) or 0,
        allow_groups=getattr(host_obj, "allow_groups", None) or [],
        deny_groups=getattr(host_obj, "deny_groups", None) or [],
    )


def _check_host_write(user: Optional[User], host_obj: Any) -> bool:
    """호스트 앱의 쓰기 권한 평가"""
    if not host_obj:
        return get_user_rank(user) >= 1
    min_read = getattr(host_obj, "min_read_rank", None)
    if min_read is None:
        min_read = getattr(host_obj, "min_rank", 0)
    return evaluate_permission(
        user=user,
        action="write",
        min_read_rank=min_read or 0,
        min_write_rank=getattr(host_obj, "min_write_rank", 2) or 0,
        allow_groups=getattr(host_obj, "allow_groups", None) or [],
        deny_groups=getattr(host_obj, "deny_groups", None) or [],
    )


def evaluate_service_permission(
    user: Optional[User],
    host_obj: Any = None,
    service_config: Optional[dict[str, Any]] = None,
    service_id: Optional[str] = None,
    app_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    [서비스앱 권한 통합 판별기 (SSOT)]
    - 우선순위: 기본값 -> ServiceApp.config.permissions -> 호스트 인스턴스(options.service_permissions)
    - 기본 조회(can_read): 호스트 앱의 읽기 권한 승계 (read_policy="inherit")
    - 기본 쓰기(can_write): 호스트 read 통과 + 로그인 + 정회원(rank >= 1) + 호스트 deny_groups(write/all) 미해당
    - 예외 처리: read_policy / write_policy로 선택형 제어
    """
    raw_app_perm = service_config.get("permissions") if isinstance(service_config, dict) else None
    perm_cfg: dict[str, Any] = dict(raw_app_perm) if isinstance(raw_app_perm, dict) else {}

    # 호스트 인스턴스(BoardConfig.options.service_permissions 등) 오버라이드 병합
    host_options = getattr(host_obj, "options", None) if host_obj else None
    if isinstance(host_options, dict):
        svc_perms = host_options.get("service_permissions")
        if isinstance(svc_perms, dict):
            for key in (service_id, str(app_id) if app_id is not None else None):
                if key and isinstance(svc_perms.get(key), dict):
                    perm_cfg.update(svc_perms[key])

    read_policy = str(perm_cfg.get("read_policy") or "inherit")
    if read_policy not in SERVICE_READ_POLICIES:
        read_policy = "inherit"

    write_policy = str(perm_cfg.get("write_policy") or "inherit_read")
    if write_policy not in SERVICE_WRITE_POLICIES:
        write_policy = "inherit_read"

    host_read_ok = _check_host_read(user, host_obj)
    user_rank = get_user_rank(user)

    # 1. 조회(can_read) 평가
    if user_rank == ROOT_RANK:
        can_read = True
    elif read_policy == "authenticated":
        can_read = host_read_ok and (user is not None)
    elif read_policy == "custom":
        can_read = host_read_ok and evaluate_permission(
            user=user,
            action="read",
            min_read_rank=int(perm_cfg.get("min_read_rank", 0) or 0),
            min_write_rank=int(perm_cfg.get("min_write_rank", 1) or 1),
            allow_groups=perm_cfg.get("allow_groups") or [],
            deny_groups=perm_cfg.get("deny_groups") or [],
        )
    else:
        can_read = host_read_ok

    # 호스트의 write/all 차단 그룹 여부 (Deny-Wins 보완)
    host_write_denied = False
    if host_obj and user is not None and user_rank != ROOT_RANK:
        deny_for_write = extract_groups_for_action(getattr(host_obj, "deny_groups", None), action="write")
        if get_user_groups(user) & deny_for_write:
            host_write_denied = True

    # 2. 쓰기(can_write) 평가 — 비로그인은 항상 쓰기 불가
    if not can_read or user is None:
        can_write = False
    elif user_rank == ROOT_RANK:
        can_write = True
    elif host_write_denied:
        can_write = False
    elif write_policy == "inherit_write":
        can_write = _check_host_write(user, host_obj)
    elif write_policy == "authenticated":
        can_write = True
    elif write_policy == "custom":
        can_write = evaluate_permission(
            user=user,
            action="write",
            min_read_rank=int(perm_cfg.get("min_read_rank", 0) or 0),
            min_write_rank=int(perm_cfg.get("min_write_rank", 1) or 1),
            allow_groups=perm_cfg.get("allow_groups") or [],
            deny_groups=perm_cfg.get("deny_groups") or [],
        )
    else:
        # inherit_read (기본값): 호스트 읽기 통과 + 정회원(1+) 이상 (또는 호스트 write allow_groups 소속)
        can_write = evaluate_permission(
            user=user,
            action="write",
            min_read_rank=0,
            min_write_rank=1,
            allow_groups=getattr(host_obj, "allow_groups", None) if host_obj else [],
            deny_groups=getattr(host_obj, "deny_groups", None) if host_obj else [],
        )

    reason: Optional[str] = None
    message: Optional[str] = None
    if not can_write:
        if user is None:
            reason = "LOGIN_REQUIRED"
            message = "로그인 후 이용할 수 있습니다."
        elif not can_read:
            reason = "FORBIDDEN"
            message = "열람 권한이 없습니다."
        elif user_rank == 0 and write_policy == "inherit_read":
            reason = "FORBIDDEN"
            message = "정회원 이상만 이용할 수 있습니다."
        else:
            reason = "FORBIDDEN"
            message = "사용 권한이 없습니다."

    return {
        "can_read": can_read,
        "can_write": can_write,
        "reason": reason,
        "message": message,
        "read_policy": read_policy,
        "write_policy": write_policy,
    }

