"""
============================================================================
[알림·지시 관리 정책 설정 서비스 (domain/alert/alert_service.py)]
============================================================================
"""

from __future__ import annotations

from typing import Any, Dict
from sqlalchemy.orm import Session

from models import SystemConfig

ALERT_SETTINGS_KEY = "alert_settings"

DEFAULT_CATEGORY_LABELS: Dict[str, str] = {
    "NOTICE": "📢 사내 공지",
    "URGENT_NOTICE": "🚨 중요 공지",
    "INSTRUCTION": "📋 지시사항",
}

DEFAULT_ALERT_SETTINGS: Dict[str, Any] = {
    "default_duration_days": 3,
    "default_level": 1,
    "default_style": "info",
    "default_confirm_text": "확인하였습니다",
    "mandatory_read_seconds": 5,
    "urgent_min_level": 3,
    "urgent_default_style": "error",
    "default_save_to_inbox": True,
    "default_send_web_push": False,
    "enable_sound": True,
    "enable_vibration": True,
    "title_max_length": 25,
    "category_labels": dict(DEFAULT_CATEGORY_LABELS),
}

ALLOWED_STYLES = {"info", "warning", "error", "success"}


def _clamp_int(value: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_val, min(max_val, num))


def normalize_alert_settings(raw: Any) -> Dict[str, Any]:
    """외부 입력/DB JSON을 검증·정규화하여 안전한 알림 정책 딕셔너리를 반환합니다."""
    src = raw if isinstance(raw, dict) else {}

    style = str(src.get("default_style") or DEFAULT_ALERT_SETTINGS["default_style"]).strip().lower()
    if style not in ALLOWED_STYLES:
        style = DEFAULT_ALERT_SETTINGS["default_style"]

    urgent_style = str(
        src.get("urgent_default_style") or DEFAULT_ALERT_SETTINGS["urgent_default_style"]
    ).strip().lower()
    if urgent_style not in ALLOWED_STYLES:
        urgent_style = DEFAULT_ALERT_SETTINGS["urgent_default_style"]

    confirm_text = str(src.get("default_confirm_text") or "").strip() or DEFAULT_ALERT_SETTINGS["default_confirm_text"]

    raw_labels = src.get("category_labels") if isinstance(src.get("category_labels"), dict) else {}
    labels: Dict[str, str] = {}
    for key, default_label in DEFAULT_CATEGORY_LABELS.items():
        val = str(raw_labels.get(key) or "").strip()
        labels[key] = val or default_label

    return {
        "default_duration_days": _clamp_int(
            src.get("default_duration_days"), 1, 90, DEFAULT_ALERT_SETTINGS["default_duration_days"]
        ),
        "default_level": _clamp_int(
            src.get("default_level"), 1, 5, DEFAULT_ALERT_SETTINGS["default_level"]
        ),
        "default_style": style,
        "default_confirm_text": confirm_text[:60],
        "mandatory_read_seconds": _clamp_int(
            src.get("mandatory_read_seconds"), 0, 30, DEFAULT_ALERT_SETTINGS["mandatory_read_seconds"]
        ),
        "urgent_min_level": _clamp_int(
            src.get("urgent_min_level"), 1, 5, DEFAULT_ALERT_SETTINGS["urgent_min_level"]
        ),
        "urgent_default_style": urgent_style,
        "default_save_to_inbox": bool(
            src.get("default_save_to_inbox", DEFAULT_ALERT_SETTINGS["default_save_to_inbox"])
        ),
        "default_send_web_push": bool(
            src.get("default_send_web_push", DEFAULT_ALERT_SETTINGS["default_send_web_push"])
        ),
        "enable_sound": bool(
            src.get("enable_sound", DEFAULT_ALERT_SETTINGS["enable_sound"])
        ),
        "enable_vibration": bool(
            src.get("enable_vibration", DEFAULT_ALERT_SETTINGS["enable_vibration"])
        ),
        "title_max_length": _clamp_int(
            src.get("title_max_length"), 10, 80, DEFAULT_ALERT_SETTINGS["title_max_length"]
        ),
        "category_labels": labels,
    }


def get_alert_settings(db: Session) -> Dict[str, Any]:
    """SystemConfig에서 알림·지시 관리 정책 설정을 조회합니다."""
    row = db.query(SystemConfig).filter(SystemConfig.key == ALERT_SETTINGS_KEY).first()
    if row and isinstance(row.value, dict):
        return normalize_alert_settings(row.value)
    return normalize_alert_settings(DEFAULT_ALERT_SETTINGS)


def update_alert_settings(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """알림·지시 관리 정책 설정을 검증 후 저장합니다."""
    clean = normalize_alert_settings(payload)
    row = db.query(SystemConfig).filter(SystemConfig.key == ALERT_SETTINGS_KEY).first()
    if row:
        row.value = clean
    else:
        db.add(
            SystemConfig(
                key=ALERT_SETTINGS_KEY,
                value=clean,
                description="알림·지시 관리(alerts) 전역 기본 정책 설정",
            )
        )
    db.commit()
    return clean


def format_alert_inbox_title(message: str, category: str, settings: Dict[str, Any]) -> str:
    """설정된 카테고리 라벨 및 요약 길이를 반영해 알림함 제목을 생성합니다."""
    labels = settings.get("category_labels") or DEFAULT_CATEGORY_LABELS
    label = labels.get(category) or DEFAULT_CATEGORY_LABELS.get(category) or DEFAULT_CATEGORY_LABELS["NOTICE"]
    max_len = int(settings.get("title_max_length") or DEFAULT_ALERT_SETTINGS["title_max_length"])
    text = (message or "").strip()
    if len(text) > max_len:
        return f"[{label}] {text[:max_len]}..."
    return f"[{label}] {text}"
