"""
============================================================================
[조직·권한 그룹 정책 설정 서비스 (domain/system/group_policy_service.py)]
============================================================================
- /v1/admin/group-manage 및 auth_group_admin_service의 비즈니스 규칙
  (보호 그룹 삭제 잠금, 사용 중 그룹 Cascade vs 차단, 1인당 부그룹 최대 개수,
   주/부그룹 유형 강제·중복 방지, 신규 생성 기본값, 감사 기록, UI 기본 탭)을
  SystemConfig('group_manage_settings') 단일 진실원으로 동적 관리합니다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models.system import SystemConfig

GROUP_SETTINGS_KEY = "group_manage_settings"

DEFAULT_GROUP_MANAGE_SETTINGS: Dict[str, Any] = {
    # 1. 그룹 삭제 보호 및 정합성 정책
    "protected_group_codes": ["admin"],
    "block_delete_in_use_group": False,
    # 2. 사용자 그룹 매칭 제약 정책
    "max_secondary_groups_per_user": 10,
    "prevent_duplicate_primary_secondary": True,
    "enforce_group_type_on_assign": False,
    # 3. 신규 그룹 생성 및 권한 기본값 정책
    "default_group_type": "PRIMARY",
    "default_group_category": "GENERAL",
    "require_group_description": False,
    "default_page_write_rank": 9,
    # 4. 감사로그 및 화면(UI) 정책
    "audit_group_changes": True,
    "ui_default_main_tab": "group",
}

VALID_GROUP_TYPES = {"PRIMARY", "SECONDARY"}
VALID_GROUP_CATEGORIES = {"GENERAL", "PRIVILEGE", "RESTRICTION"}
VALID_MAIN_TABS = {"group", "user", "instance", "system-app"}


def _clamp_int(value: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_val, min(max_val, num))


def _normalize_code_list(raw: Any, fallback: List[str], max_items: int = 40) -> List[str]:
    if not isinstance(raw, list):
        return list(fallback)
    seen = set()
    cleaned: List[str] = []
    for item in raw:
        s = str(item or "").strip()
        if not s or len(s) > 50 or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
        if len(cleaned) >= max_items:
            break
    return cleaned


def normalize_group_manage_settings(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    def_type = str(src.get("default_group_type") or DEFAULT_GROUP_MANAGE_SETTINGS["default_group_type"]).strip().upper()
    if def_type not in VALID_GROUP_TYPES:
        def_type = DEFAULT_GROUP_MANAGE_SETTINGS["default_group_type"]

    def_cat = str(src.get("default_group_category") or DEFAULT_GROUP_MANAGE_SETTINGS["default_group_category"]).strip().upper()
    if def_cat not in VALID_GROUP_CATEGORIES:
        def_cat = DEFAULT_GROUP_MANAGE_SETTINGS["default_group_category"]

    def_tab = str(src.get("ui_default_main_tab") or DEFAULT_GROUP_MANAGE_SETTINGS["ui_default_main_tab"]).strip().lower()
    if def_tab not in VALID_MAIN_TABS:
        def_tab = DEFAULT_GROUP_MANAGE_SETTINGS["ui_default_main_tab"]

    return {
        "protected_group_codes": _normalize_code_list(
            src.get("protected_group_codes"),
            DEFAULT_GROUP_MANAGE_SETTINGS["protected_group_codes"],
        ),
        "block_delete_in_use_group": bool(
            src.get("block_delete_in_use_group", DEFAULT_GROUP_MANAGE_SETTINGS["block_delete_in_use_group"])
        ),
        "max_secondary_groups_per_user": _clamp_int(
            src.get("max_secondary_groups_per_user"),
            1,
            50,
            DEFAULT_GROUP_MANAGE_SETTINGS["max_secondary_groups_per_user"],
        ),
        "prevent_duplicate_primary_secondary": bool(
            src.get(
                "prevent_duplicate_primary_secondary",
                DEFAULT_GROUP_MANAGE_SETTINGS["prevent_duplicate_primary_secondary"],
            )
        ),
        "enforce_group_type_on_assign": bool(
            src.get(
                "enforce_group_type_on_assign",
                DEFAULT_GROUP_MANAGE_SETTINGS["enforce_group_type_on_assign"],
            )
        ),
        "default_group_type": def_type,
        "default_group_category": def_cat,
        "require_group_description": bool(
            src.get("require_group_description", DEFAULT_GROUP_MANAGE_SETTINGS["require_group_description"])
        ),
        "default_page_write_rank": _clamp_int(
            src.get("default_page_write_rank"),
            0,
            9,
            DEFAULT_GROUP_MANAGE_SETTINGS["default_page_write_rank"],
        ),
        "audit_group_changes": bool(
            src.get("audit_group_changes", DEFAULT_GROUP_MANAGE_SETTINGS["audit_group_changes"])
        ),
        "ui_default_main_tab": def_tab,
    }


def get_group_manage_settings(db: Session) -> Dict[str, Any]:
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == GROUP_SETTINGS_KEY).first()
    except Exception:
        return normalize_group_manage_settings(DEFAULT_GROUP_MANAGE_SETTINGS)

    if row and isinstance(row.value, dict):
        return normalize_group_manage_settings(row.value)
    return normalize_group_manage_settings(DEFAULT_GROUP_MANAGE_SETTINGS)


def update_group_manage_settings(db: Session, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    old_cfg = get_group_manage_settings(db)
    clean = normalize_group_manage_settings(payload)

    row = db.query(SystemConfig).filter(SystemConfig.key == GROUP_SETTINGS_KEY).first()
    if row:
        row.value = clean
        flag_modified(row, "value")
    else:
        db.add(
            SystemConfig(
                key=GROUP_SETTINGS_KEY,
                value=clean,
                description="조직·권한 그룹 관리 통합 정책 설정 (JSON)",
            )
        )

    db.commit()
    return old_cfg, clean
