"""
============================================================================
[비동기 태스크·자율신경계 동적 정책 서비스 (domain/system/task_policy_service.py)]
============================================================================
- SystemConfig(key="task_settings")를 단일 진실 공급원(SSOT)으로 삼아
  워커 엔진 가동/일시정지, 폴링·고착회수 주기, 기본 우선순위·재시도·타임아웃·지수 백오프,
  태스크 이력 보존기한, 연속 실패 경보 임계치, 6대 핵심 스케줄러 주기, 관제 UI 기본값 및
  전체 9종 핸들러 한글 메타데이터를 통합 관리합니다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import SystemConfig, SystemTask

logger = logging.getLogger("task_policy_service")

TASK_SETTINGS_KEY = "task_settings"

# 📋 전체 9종 등록 핸들러 한글 메타데이터 SSOT (누락되어 있던 4대 자율신경계 핸들러 완비)
DEFAULT_TASK_METADATA: Dict[str, Dict[str, Any]] = {
    "DISPATCH_AUTO_ANNOUNCE": {
        "label": "명일 배차 자동 확정·고지",
        "description": "설정된 D-1 배차 공개 시각 도래 시 명일 배차를 자동 확정하고 승무원에게 알림·웹푸시를 발송합니다.",
        "category": "배차/동기화",
        "icon": "solar:bus-bold-duotone",
        "example": {},
    },
    "DYNAMIC_GROUP_REFRESH": {
        "label": "오늘 운행·휴무 기사 그룹 동기화",
        "description": "당일 배차 및 승인된 휴무 일정과 대조하여 알림 타겟팅용 동적 승무원 그룹을 최신화합니다.",
        "category": "배차/동기화",
        "icon": "solar:users-group-two-rounded-bold-duotone",
        "example": {},
    },
    "CHECK_MINIAPP_ALARMS": {
        "label": "미니앱 리마인더 알람 감시·발송",
        "description": "예약 시각이 도래한 미니앱 개인/업무 알람을 감지하여 백그라운드 Web Push 및 실시간 신호를 보냅니다.",
        "category": "알림/리마인더",
        "icon": "solar:bell-bing-bold-duotone",
        "example": {},
    },
    "SYSTEM_WATCHDOG_INSPECTION": {
        "label": "시스템 이상징후 자율 감시 (Watchdog)",
        "description": "워커 연속 실패, 보안 침해 로그, 긴급 지시 미확인 지연 등 전사 이상 징후를 주기적으로 점검합니다.",
        "category": "보안/관제",
        "icon": "solar:shield-check-bold-duotone",
        "example": {},
    },
    "DATA_RETENTION_GC": {
        "label": "전사 만료 이력·Redis 메모리 청소",
        "description": "보존 기한이 지난 감사로그, 만료 세션, 완료 태스크 이력 및 Redis 고아 키를 자동 정리합니다.",
        "category": "정리/보관",
        "icon": "solar:database-bold-duotone",
        "example": {},
    },
    "MEDIA_GC": {
        "label": "미디어 스토리지 가비지 컬렉션",
        "description": "고립 파일, 유령 레코드, 만료된 삭제 격리(.DEL_) 파일 및 시한부 원본 이미지를 안전하게 정리합니다.",
        "category": "정리/보관",
        "icon": "solar:broom-bold-duotone",
        "example": {"indices": [1, 2, 3, 4, 5, 6]},
    },
    "THUMB_GEN": {
        "label": "고해상도 사진 썸네일 생성",
        "description": "업로드된 원본 이미지를 모바일·웹에서 초고속으로 서빙하기 위한 WebP 축소판(SM/MD/LG)을 생성합니다.",
        "category": "미디어",
        "icon": "solar:gallery-wide-bold-duotone",
        "example": {"asset_id": 1},
    },
    "MEDIA_BACKUP": {
        "label": "중요 사진·파일 안전 백업",
        "description": "선택된 미디어 자산을 관리자 개인 보관함(ADMIN_BACKUPS)으로 복제하여 안전하게 백업합니다.",
        "category": "정리/보관",
        "icon": "solar:box-archive-bold-duotone",
        "example": {"asset_ids": [1, 2], "target_user_id": 1},
    },
    "MEDIA_ISOLATE": {
        "label": "삭제 파일 숨김 검역·격리",
        "description": "소프트 삭제된 파일과 썸네일 세트에 .DEL_ 접두어를 부여하여 외부 접근으로부터 즉시 격리합니다.",
        "category": "보안/관제",
        "icon": "solar:shield-warning-bold-duotone",
        "example": {"file_path": "/app/uploads/PUBLIC/sample.jpg", "asset_id": 1},
    },
}

DEFAULT_CORE_SCHEDULES: List[Dict[str, Any]] = [
    {
        "task_type": "DYNAMIC_GROUP_REFRESH",
        "unique_key": "cron:dynamic_group_refresh",
        "label": "오늘 운행·휴무 기사 그룹 동기화",
        "enabled": True,
        "mode": "cron",
        "cron_expression": "0 7 * * *",
        "repeat_interval": None,
        "priority": 3,
        "payload": {},
        "tags": ["core", "dynamic_group", "cron"],
    },
    {
        "task_type": "SYSTEM_WATCHDOG_INSPECTION",
        "unique_key": "cron:system_watchdog_inspection",
        "label": "시스템 이상징후 자율 감시 (Watchdog)",
        "enabled": True,
        "mode": "interval",
        "cron_expression": None,
        "repeat_interval": 300,
        "priority": 2,
        "payload": {},
        "tags": ["core", "watchdog", "cron"],
    },
    {
        "task_type": "DATA_RETENTION_GC",
        "unique_key": "cron:data_retention_gc",
        "label": "전사 만료 이력·Redis 메모리 청소",
        "enabled": True,
        "mode": "cron",
        "cron_expression": "0 3 * * *",
        "repeat_interval": None,
        "priority": 8,
        "payload": {},
        "tags": ["core", "retention", "gc", "cron"],
    },
    {
        "task_type": "MEDIA_GC",
        "unique_key": "cron:media_gc",
        "label": "미디어 스토리지 가비지 컬렉션",
        "enabled": True,
        "mode": "cron",
        "cron_expression": "0 4 * * *",
        "repeat_interval": None,
        "priority": 8,
        "payload": {"indices": [1, 2, 3, 4, 5, 6]},
        "tags": ["core", "media", "gc", "cron"],
    },
    {
        "task_type": "CHECK_MINIAPP_ALARMS",
        "unique_key": "cron:check_miniapp_alarms",
        "label": "미니앱 리마인더 알람 감시·발송",
        "enabled": True,
        "mode": "interval",
        "cron_expression": None,
        "repeat_interval": 60,
        "priority": 1,
        "payload": {},
        "tags": ["core", "miniapp", "alarm", "cron"],
    },
    {
        "task_type": "DISPATCH_AUTO_ANNOUNCE",
        "unique_key": "cron:dispatch_auto_announce",
        "label": "명일 배차 자동 확정·고지 감시",
        "enabled": True,
        "mode": "interval",
        "cron_expression": None,
        "repeat_interval": 60,
        "priority": 2,
        "payload": {},
        "tags": ["core", "dispatch", "announce", "cron"],
    },
]

DEFAULT_CRON_PRESETS: List[Dict[str, str]] = [
    {"label": "매일 새벽 3시 (야간 청소)", "cron": "0 3 * * *", "desc": "이용자가 적은 새벽에 시스템 정리"},
    {"label": "매일 새벽 4시 (미디어 GC)", "cron": "0 4 * * *", "desc": "스토리지 미아/만료 파일 정리"},
    {"label": "매일 아침 7시 (출근 전 준비)", "cron": "0 7 * * *", "desc": "오늘 운행 기사님 단체방 준비"},
    {"label": "매 시간 정각마다", "cron": "0 * * * *", "desc": "1시간 주기 정기 상태 점검"},
    {"label": "10분마다 주기적 반복", "cron": "*/10 * * * *", "desc": "실시간에 준하는 고빈도 동기화"},
]

DEFAULT_TASK_SETTINGS: Dict[str, Any] = {
    # 1. 워커 엔진 가동·폴링·자가치유 정책
    "worker_enabled": True,
    "worker_poll_interval_sec": 2,
    "reclaim_check_interval_sec": 60,
    "bootstrap_heal_stuck_sec": 600,

    # 2. 신규 태스크 기본값 및 재시도 백오프 정책
    "default_priority": 5,
    "default_max_retries": 3,
    "default_timeout_sec": 300,
    "retry_backoff_base_sec": 10,
    "retry_backoff_max_sec": 300,

    # 3. 보존 기한 및 연속 실패 경보(Watchdog) 정책
    "completed_retention_days": 30,
    "watchdog_fail_alert_enabled": True,
    "watchdog_fail_threshold": 3,

    # 4. 6대 핵심 자율신경계 정기 스케줄 설정
    "core_schedules": [dict(item) for item in DEFAULT_CORE_SCHEDULES],

    # 5. 관제 화면(UI) 및 프리셋 정책
    "ui_auto_refresh_default": True,
    "ui_auto_refresh_sec": 10,
    "ui_page_limit": 50,
    "cron_presets": [dict(item) for item in DEFAULT_CRON_PRESETS],
}

# 워커 무한 루프 DB 부하 방지용 단기 메모리 캐시 (TTL 5초, 저장 시 즉시 무효화)
_WORKER_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_TTL_SEC = 5.0


def invalidate_task_settings_cache() -> None:
    _WORKER_CACHE["ts"] = 0.0
    _WORKER_CACHE["data"] = None


def _clamp_int(value: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_val, min(max_val, num))


def _normalize_core_schedules(raw: Any) -> List[Dict[str, Any]]:
    raw_by_key: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("unique_key"):
                raw_by_key[str(item["unique_key"])] = item

    normalized: List[Dict[str, Any]] = []
    for default_item in DEFAULT_CORE_SCHEDULES:
        ukey = default_item["unique_key"]
        incoming = raw_by_key.get(ukey, {})
        mode = str(incoming.get("mode") or default_item["mode"]).strip().lower()
        if mode not in ("cron", "interval"):
            mode = default_item["mode"]

        cron_val = str(incoming.get("cron_expression") or "").strip() or None
        interval_val = incoming.get("repeat_interval")
        if mode == "cron":
            if not cron_val:
                cron_val = default_item["cron_expression"] or "0 3 * * *"
            interval_clean = None
        else:
            cron_val = None
            interval_clean = _clamp_int(
                interval_val, 10, 86400, default_item["repeat_interval"] or 60
            )

        normalized.append(
            {
                "task_type": default_item["task_type"],
                "unique_key": ukey,
                "label": str(incoming.get("label") or default_item["label"]).strip()[:60],
                "enabled": bool(incoming.get("enabled", default_item["enabled"])),
                "mode": mode,
                "cron_expression": cron_val,
                "repeat_interval": interval_clean,
                "priority": _clamp_int(incoming.get("priority"), 1, 10, default_item["priority"]),
                "payload": default_item["payload"],
                "tags": default_item["tags"],
            }
        )
    return normalized


def _normalize_cron_presets(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_CRON_PRESETS]
    cleaned: List[Dict[str, str]] = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        cron = str(item.get("cron") or "").strip()
        desc = str(item.get("desc") or "").strip()
        if label and len(cron.split()) == 5:
            cleaned.append({"label": label[:40], "cron": cron[:40], "desc": desc[:80]})
    return cleaned if cleaned else [dict(item) for item in DEFAULT_CRON_PRESETS]


def normalize_task_settings(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    backoff_base = _clamp_int(
        src.get("retry_backoff_base_sec"), 2, 120, DEFAULT_TASK_SETTINGS["retry_backoff_base_sec"]
    )
    backoff_max = _clamp_int(
        src.get("retry_backoff_max_sec"),
        max(backoff_base, 30),
        3600,
        DEFAULT_TASK_SETTINGS["retry_backoff_max_sec"],
    )

    return {
        "worker_enabled": bool(src.get("worker_enabled", DEFAULT_TASK_SETTINGS["worker_enabled"])),
        "worker_poll_interval_sec": _clamp_int(
            src.get("worker_poll_interval_sec"), 1, 60, DEFAULT_TASK_SETTINGS["worker_poll_interval_sec"]
        ),
        "reclaim_check_interval_sec": _clamp_int(
            src.get("reclaim_check_interval_sec"), 10, 600, DEFAULT_TASK_SETTINGS["reclaim_check_interval_sec"]
        ),
        "bootstrap_heal_stuck_sec": _clamp_int(
            src.get("bootstrap_heal_stuck_sec"), 60, 3600, DEFAULT_TASK_SETTINGS["bootstrap_heal_stuck_sec"]
        ),
        "default_priority": _clamp_int(
            src.get("default_priority"), 1, 10, DEFAULT_TASK_SETTINGS["default_priority"]
        ),
        "default_max_retries": _clamp_int(
            src.get("default_max_retries"), 0, 10, DEFAULT_TASK_SETTINGS["default_max_retries"]
        ),
        "default_timeout_sec": _clamp_int(
            src.get("default_timeout_sec"), 10, 3600, DEFAULT_TASK_SETTINGS["default_timeout_sec"]
        ),
        "retry_backoff_base_sec": backoff_base,
        "retry_backoff_max_sec": backoff_max,
        "completed_retention_days": _clamp_int(
            src.get("completed_retention_days"), 1, 365, DEFAULT_TASK_SETTINGS["completed_retention_days"]
        ),
        "watchdog_fail_alert_enabled": bool(
            src.get("watchdog_fail_alert_enabled", DEFAULT_TASK_SETTINGS["watchdog_fail_alert_enabled"])
        ),
        "watchdog_fail_threshold": _clamp_int(
            src.get("watchdog_fail_threshold"), 1, 20, DEFAULT_TASK_SETTINGS["watchdog_fail_threshold"]
        ),
        "core_schedules": _normalize_core_schedules(src.get("core_schedules")),
        "ui_auto_refresh_default": bool(
            src.get("ui_auto_refresh_default", DEFAULT_TASK_SETTINGS["ui_auto_refresh_default"])
        ),
        "ui_auto_refresh_sec": _clamp_int(
            src.get("ui_auto_refresh_sec"), 3, 120, DEFAULT_TASK_SETTINGS["ui_auto_refresh_sec"]
        ),
        "ui_page_limit": _clamp_int(
            src.get("ui_page_limit"), 10, 200, DEFAULT_TASK_SETTINGS["ui_page_limit"]
        ),
        "cron_presets": _normalize_cron_presets(src.get("cron_presets")),
    }


def _upsert_scalar_config(db: Session, key: str, val: Any, desc: str) -> None:
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row:
        row.value = val
    else:
        db.add(SystemConfig(key=key, value=val, description=desc))


def get_task_settings(db: Session) -> Dict[str, Any]:
    """DB에서 task_settings를 조회하며, 테이블 미생성 환경(단위 테스트 등)에서는 기본값으로 안전 폴백합니다."""
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == TASK_SETTINGS_KEY).first()
        if row and isinstance(row.value, dict):
            return normalize_task_settings(row.value)

        merged = dict(DEFAULT_TASK_SETTINGS)
        legacy_rows = (
            db.query(SystemConfig)
            .filter(SystemConfig.key.in_(["retention_system_task_days", "watchdog_fail_threshold", "watchdog_enabled"]))
            .all()
        )
        for r in legacy_rows:
            v = r.value.get("value") if isinstance(r.value, dict) and "value" in r.value else r.value
            if r.key == "retention_system_task_days":
                merged["completed_retention_days"] = v
            elif r.key == "watchdog_fail_threshold":
                merged["watchdog_fail_threshold"] = v
            elif r.key == "watchdog_enabled":
                merged["watchdog_fail_alert_enabled"] = v

        return normalize_task_settings(merged)
    except Exception:
        return normalize_task_settings(DEFAULT_TASK_SETTINGS)


def get_cached_task_settings(db: Session) -> Dict[str, Any]:
    """워커 무한 루프 전용 5초 TTL 캐시 조회"""
    now_mono = time.monotonic()
    if _WORKER_CACHE["data"] is not None and (now_mono - _WORKER_CACHE["ts"]) < _CACHE_TTL_SEC:
        return _WORKER_CACHE["data"]
    settings = get_task_settings(db)
    _WORKER_CACHE["data"] = settings
    _WORKER_CACHE["ts"] = now_mono
    return settings


def sync_core_schedules_to_db(db: Session, settings: Dict[str, Any]) -> None:
    """
    설정 탭에서 변경된 6대 핵심 스케줄러 사양(활성화 여부, Cron/Interval, 우선순위)을
    실제 system_tasks 테이블의 활성 정기 작업 레코드에 즉시 반영합니다.
    (레거시 unique_key=None 반복 행도 흡수·정규화하여 중복 생성을 원천 방지)
    """
    from sqlalchemy import or_
    from domain.system.task_service import calculate_next_scheduled_at

    now = datetime.now()
    for item in settings.get("core_schedules", []):
        ukey_prefix = item["unique_key"]
        active_tasks = (
            db.query(SystemTask)
            .filter(
                SystemTask.task_type == item["task_type"],
                or_(SystemTask.cron_expression.is_not(None), SystemTask.repeat_interval.is_not(None)),
                or_(SystemTask.unique_key.like(f"{ukey_prefix}%"), SystemTask.unique_key.is_(None)),
                SystemTask.status.in_(["PENDING", "CANCELLED"]),
            )
            .order_by(SystemTask.id.desc())
            .all()
        )
        pending_tasks = [t for t in active_tasks if t.status == "PENDING"]
        target: Optional[SystemTask] = pending_tasks[0] if pending_tasks else None

        # 중복 PENDING 정기 행이 2개 이상이면 최신 대표 1건만 남기고 잉여 레코드 정리
        for dup in pending_tasks[1:]:
            db.delete(dup)

        if not item.get("enabled", True):
            if target:
                target.status = "CANCELLED"
            continue

        next_time = (
            calculate_next_scheduled_at(
                cron_expr=item["cron_expression"],
                interval_sec=item["repeat_interval"],
                base_time=now,
            )
            or now
        )

        if target:
            changed = (
                target.cron_expression != item["cron_expression"]
                or target.repeat_interval != item["repeat_interval"]
                or target.priority != item["priority"]
            )
            target.cron_expression = item["cron_expression"]
            target.repeat_interval = item["repeat_interval"]
            target.priority = item["priority"]
            if not target.unique_key:
                target.unique_key = f"{ukey_prefix}:{next_time.strftime('%Y%m%d%H%M%S')}"
            if changed:
                target.scheduled_at = next_time
        else:
            # 취소되었거나 없는 경우 새로 PENDING 발행
            reusable = next((t for t in active_tasks if t.status == "CANCELLED"), None)
            if reusable and reusable.unique_key == ukey_prefix:
                reusable.status = "PENDING"
                reusable.cron_expression = item["cron_expression"]
                reusable.repeat_interval = item["repeat_interval"]
                reusable.priority = item["priority"]
                reusable.scheduled_at = next_time
                reusable.retry_count = 0
                reusable.error_log = None
            else:
                new_key = f"{ukey_prefix}:{next_time.strftime('%Y%m%d%H%M%S')}"
                db.add(
                    SystemTask(
                        task_type=item["task_type"],
                        payload=item["payload"],
                        priority=item["priority"],
                        scheduled_at=next_time,
                        cron_expression=item["cron_expression"],
                        repeat_interval=item["repeat_interval"],
                        unique_key=new_key,
                        tags=item["tags"],
                        max_retries=int(settings.get("default_max_retries", 3)),
                        timeout_sec=int(settings.get("default_timeout_sec", 300)),
                        status="PENDING",
                    )
                )


def update_task_settings(db: Session, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """태스크 관리 정책을 검증·저장하고, 연관 SystemConfig 및 DB 정기 스케줄까지 원자적으로 동기화합니다."""
    old_settings = get_task_settings(db)
    clean = normalize_task_settings(payload)

    row = db.query(SystemConfig).filter(SystemConfig.key == TASK_SETTINGS_KEY).first()
    if row:
        row.value = clean
        flag_modified(row, "value")
    else:
        db.add(
            SystemConfig(
                key=TASK_SETTINGS_KEY,
                value=clean,
                description="비동기 태스크 워커·자율신경계 스케줄러 통합 정책 설정 (JSON)",
            )
        )

    # retention_service 및 watchdog_service와 호환되도록 기존 스칼라 키도 함께 동기화
    _upsert_scalar_config(
        db,
        "retention_system_task_days",
        clean["completed_retention_days"],
        "완료/실패 시스템 태스크 이력 보존 기간 (일)",
    )
    _upsert_scalar_config(
        db,
        "watchdog_fail_threshold",
        clean["watchdog_fail_threshold"],
        "최근 1시간 내 연속 실패 태스크 경보 임계치",
    )

    sync_core_schedules_to_db(db, clean)
    db.commit()
    invalidate_task_settings_cache()
    return old_settings, clean
