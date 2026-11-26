"""
============================================================================
[통합 관제·감사로그 정책 설정 서비스 (domain/system/observability_policy_service.py)]
============================================================================
- /v1/admin/observability, watchdog_service, retention_service, core/audit.py에
  흩어져 있던 하드코딩 상수(쿨다운, 임계치, 보존 일수, 마스킹 필드, CSV/콘솔로그 제한,
  대시보드 자동갱신·페이징)를 SystemConfig('observability_settings') 단일 진실원으로 통합합니다.
- 기존 스칼라 SystemConfig 키(watchdog_enabled, watchdog_security_alert,
  watchdog_instruction_delay_minutes, retention_audit_log_days,
  retention_session_history_days)와 양방향 호환 동기화를 유지합니다.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models.system import SystemConfig

OBSERVABILITY_SETTINGS_KEY = "observability_settings"

# 코어에서 항상 보호하는 기본 민감 마스킹 키워드 (삭제 불가)
BUILTIN_MASK_FIELDS: List[str] = [
    "password",
    "resident_no",
    "account_no",
    "secret",
    "token",
    "session_key",
    "credit_card",
]

DEFAULT_IGNORE_SECURITY_ACTIONS: List[str] = [
    "SESSION_KICKED",
    "SESSION_REVOKED",
    "ADMIN_KICK",
    "PERM_CHANGED",
    "LOGIN_SUCCESS",
    "LOGOUT",
    "LOG_EXPORT_CSV",
    "SYSTEM_LOG_DOWNLOAD",
]

DEFAULT_OBSERVABILITY_SETTINGS: Dict[str, Any] = {
    # 1. 자율 감시(Watchdog) & 경보 정책
    "watchdog_enabled": True,
    "watchdog_security_alert": True,
    "watchdog_cooldown_minutes": 15,
    "watchdog_instruction_delay_minutes": 30,
    "watchdog_instruction_min_count": 3,
    "security_alert_ignore_actions": list(DEFAULT_IGNORE_SECURITY_ACTIONS),
    # 2. 이력 보존(Retention GC) 정책
    "audit_log_retention_days": 180,
    "session_history_retention_days": 60,
    # 3. 감사로그 민감정보 마스킹 정책
    "audit_mask_sensitive_fields": True,
    "audit_extra_mask_fields": [],
    # 4. CSV 내보내기 & 시스템 콘솔 로그 다운로드 정책
    "allow_csv_export": True,
    "csv_export_max_rows": 5000,
    "allow_system_log_download": True,
    "system_log_max_download_mb": 10,
    # 5. 관제 대시보드 UI 정책
    "ui_auto_refresh_default": True,
    "ui_auto_refresh_sec": 10,
    "ui_log_page_size": 20,
    "ui_session_history_limit": 100,
}

# 고빈도 로깅/감시 경로를 위한 경량 인메모리 캐시 (TTL 10초)
_OBS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_OBS_CACHE_TTL_SEC = 10.0


def invalidate_observability_settings_cache() -> None:
    _OBS_CACHE["ts"] = 0.0
    _OBS_CACHE["data"] = None


def _clamp_int(value: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_val, min(max_val, num))


def _normalize_str_list(raw: Any, fallback: List[str], *, uppercase: bool = False, max_items: int = 40) -> List[str]:
    if not isinstance(raw, list):
        return list(fallback)
    seen = set()
    result: List[str] = []
    for item in raw:
        s = str(item or "").strip()
        if not s:
            continue
        s = s.upper() if uppercase else s.lower()
        if len(s) > 64 or s in seen:
            continue
        seen.add(s)
        result.append(s)
        if len(result) >= max_items:
            break
    return result


def normalize_observability_settings(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    ignore_actions = _normalize_str_list(
        src.get("security_alert_ignore_actions"),
        DEFAULT_IGNORE_SECURITY_ACTIONS,
        uppercase=True,
        max_items=50,
    )
    extra_masks = _normalize_str_list(
        src.get("audit_extra_mask_fields"),
        [],
        uppercase=False,
        max_items=30,
    )

    return {
        "watchdog_enabled": bool(src.get("watchdog_enabled", DEFAULT_OBSERVABILITY_SETTINGS["watchdog_enabled"])),
        "watchdog_security_alert": bool(
            src.get("watchdog_security_alert", DEFAULT_OBSERVABILITY_SETTINGS["watchdog_security_alert"])
        ),
        "watchdog_cooldown_minutes": _clamp_int(
            src.get("watchdog_cooldown_minutes"), 1, 120, DEFAULT_OBSERVABILITY_SETTINGS["watchdog_cooldown_minutes"]
        ),
        "watchdog_instruction_delay_minutes": _clamp_int(
            src.get("watchdog_instruction_delay_minutes"),
            5,
            240,
            DEFAULT_OBSERVABILITY_SETTINGS["watchdog_instruction_delay_minutes"],
        ),
        "watchdog_instruction_min_count": _clamp_int(
            src.get("watchdog_instruction_min_count"),
            1,
            50,
            DEFAULT_OBSERVABILITY_SETTINGS["watchdog_instruction_min_count"],
        ),
        "security_alert_ignore_actions": ignore_actions,
        "audit_log_retention_days": _clamp_int(
            src.get("audit_log_retention_days"),
            7,
            3650,
            DEFAULT_OBSERVABILITY_SETTINGS["audit_log_retention_days"],
        ),
        "session_history_retention_days": _clamp_int(
            src.get("session_history_retention_days"),
            7,
            365,
            DEFAULT_OBSERVABILITY_SETTINGS["session_history_retention_days"],
        ),
        "audit_mask_sensitive_fields": bool(
            src.get("audit_mask_sensitive_fields", DEFAULT_OBSERVABILITY_SETTINGS["audit_mask_sensitive_fields"])
        ),
        "audit_extra_mask_fields": extra_masks,
        "allow_csv_export": bool(src.get("allow_csv_export", DEFAULT_OBSERVABILITY_SETTINGS["allow_csv_export"])),
        "csv_export_max_rows": _clamp_int(
            src.get("csv_export_max_rows"), 100, 50000, DEFAULT_OBSERVABILITY_SETTINGS["csv_export_max_rows"]
        ),
        "allow_system_log_download": bool(
            src.get("allow_system_log_download", DEFAULT_OBSERVABILITY_SETTINGS["allow_system_log_download"])
        ),
        "system_log_max_download_mb": _clamp_int(
            src.get("system_log_max_download_mb"),
            1,
            100,
            DEFAULT_OBSERVABILITY_SETTINGS["system_log_max_download_mb"],
        ),
        "ui_auto_refresh_default": bool(
            src.get("ui_auto_refresh_default", DEFAULT_OBSERVABILITY_SETTINGS["ui_auto_refresh_default"])
        ),
        "ui_auto_refresh_sec": _clamp_int(
            src.get("ui_auto_refresh_sec"), 3, 120, DEFAULT_OBSERVABILITY_SETTINGS["ui_auto_refresh_sec"]
        ),
        "ui_log_page_size": _clamp_int(
            src.get("ui_log_page_size"), 10, 100, DEFAULT_OBSERVABILITY_SETTINGS["ui_log_page_size"]
        ),
        "ui_session_history_limit": _clamp_int(
            src.get("ui_session_history_limit"),
            20,
            500,
            DEFAULT_OBSERVABILITY_SETTINGS["ui_session_history_limit"],
        ),
    }


def _extract_scalar(val: Any) -> Any:
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def _upsert_scalar_config(db: Session, key: str, value: Any, description: str) -> None:
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row:
        row.value = value
        flag_modified(row, "value")
    else:
        db.add(SystemConfig(key=key, value=value, description=description))


def get_observability_settings(db: Session) -> Dict[str, Any]:
    """DB에서 통합 관제 정책을 조회하며, 최초 미존재 시 기존 스칼라 키를 안전하게 흡수합니다."""
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == OBSERVABILITY_SETTINGS_KEY).first()
    except Exception:
        return normalize_observability_settings(DEFAULT_OBSERVABILITY_SETTINGS)

    if row and isinstance(row.value, dict):
        return normalize_observability_settings(row.value)

    # 레거시 스칼라 키 Fallback 흡수
    merged = dict(DEFAULT_OBSERVABILITY_SETTINGS)
    scalar_map = {
        "watchdog_enabled": "watchdog_enabled",
        "watchdog_security_alert": "watchdog_security_alert",
        "watchdog_instruction_delay_minutes": "watchdog_instruction_delay_minutes",
        "retention_audit_log_days": "audit_log_retention_days",
        "retention_session_history_days": "session_history_retention_days",
    }
    try:
        rows = db.query(SystemConfig).filter(SystemConfig.key.in_(list(scalar_map.keys()))).all()
        for cfg in rows:
            target_field = scalar_map.get(cfg.key)
            if target_field:
                merged[target_field] = _extract_scalar(cfg.value)
    except Exception:
        pass

    return normalize_observability_settings(merged)


def get_cached_observability_settings(db: Session | None = None) -> Dict[str, Any]:
    """고빈도 감사 마스킹/Watchdog 체크에서 DB 조회를 최소화하는 10초 캐시 조회"""
    now = time.monotonic()
    if _OBS_CACHE["data"] is not None and (now - _OBS_CACHE["ts"]) < _OBS_CACHE_TTL_SEC:
        return _OBS_CACHE["data"]

    if db is None:
        return _OBS_CACHE["data"] or normalize_observability_settings(DEFAULT_OBSERVABILITY_SETTINGS)

    data = get_observability_settings(db)
    _OBS_CACHE["data"] = data
    _OBS_CACHE["ts"] = now
    return data


def update_observability_settings(db: Session, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """관제 정책을 검증·저장하고, Watchdog 및 Retention 스칼라 키와 양방향 동기화합니다."""
    old_cfg = get_observability_settings(db)
    clean = normalize_observability_settings(payload)

    row = db.query(SystemConfig).filter(SystemConfig.key == OBSERVABILITY_SETTINGS_KEY).first()
    if row:
        row.value = clean
        flag_modified(row, "value")
    else:
        db.add(
            SystemConfig(
                key=OBSERVABILITY_SETTINGS_KEY,
                value=clean,
                description="통합 관제·감사로그·세션·Watchdog 통합 정책 설정 (JSON)",
            )
        )

    # 레거시/연관 스칼라 키 양방향 동기화
    _upsert_scalar_config(db, "watchdog_enabled", clean["watchdog_enabled"], "자율 감시(Watchdog) 엔진 활성화 여부")
    _upsert_scalar_config(
        db, "watchdog_security_alert", clean["watchdog_security_alert"], "보안 침해(403) 감지 시 즉시 경보 여부"
    )
    _upsert_scalar_config(
        db,
        "watchdog_instruction_delay_minutes",
        clean["watchdog_instruction_delay_minutes"],
        "현장 지시사항 미확인 지연 기준 시간(분)",
    )
    _upsert_scalar_config(
        db, "retention_audit_log_days", clean["audit_log_retention_days"], "전사 감사로그 DB 보존 기간(일)"
    )
    _upsert_scalar_config(
        db,
        "retention_session_history_days",
        clean["session_history_retention_days"],
        "만료·추방 세션 이력 DB 보존 기간(일)",
    )

    db.commit()
    invalidate_observability_settings_cache()
    # 즉시 캐시 워밍
    _OBS_CACHE["data"] = clean
    _OBS_CACHE["ts"] = time.monotonic()
    return old_cfg, clean
