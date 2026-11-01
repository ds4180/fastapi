"""
============================================================================
[자율신경계 이상 징후 감시 및 자동 경보 엔진 (domain/system/watchdog_service.py)]
============================================================================

💡 이 파일의 역할:
시스템 내부의 이상 징후(워커 연속 실패, 403 보안 침해 시도, 현장 지시 미확인 지연)를
자율 감시하고, 임계치를 초과할 경우 최고 관리자 그룹에게 즉시 L4 긴급 경보(core.notify)를
자동 발행하는 무인 자율 관제(Watchdog) 서비스입니다.
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from models.system import SystemConfig, SystemTask
from models.audit import AuditLog
from models.miniapp import MiniappItem
from core.notify import safe_notify

logger = logging.getLogger("system.watchdog")

# ⚙️ 기본 감시 임계치 및 정책 규격
DEFAULT_WATCHDOG_CONFIG: Dict[str, Any] = {
    "watchdog_enabled": True,                 # 감시 엔진 전체 활성화 여부
    "watchdog_fail_threshold": 3,             # 연속 FAILED 태스크 감지 임계치
    "watchdog_security_alert": True,          # 403 보안 감사로그 감지 즉시 경보
    "watchdog_instruction_delay_minutes": 30  # 긴급 지시 미확인 지연 기준 시간 (분)
}

# 🛡️ 메모리 기반 중복 경보 방지 쿨다운 딕셔너리 (Key: alarm_type, Value: datetime)
_COOLDOWN_MAP: Dict[str, datetime] = {}
COOLDOWN_MINUTES = 15  # 동일 경보 15분 내 중복 발송 방지


def _is_in_cooldown(alarm_type: str) -> bool:
    """동일 경보의 쿨다운 경과 여부 확인"""
    last_time = _COOLDOWN_MAP.get(alarm_type)
    if not last_time:
        return False
    if datetime.now() - last_time < timedelta(minutes=COOLDOWN_MINUTES):
        return True
    return False


def _set_cooldown(alarm_type: str):
    """쿨다운 타임스탬프 기록"""
    _COOLDOWN_MAP[alarm_type] = datetime.now()


def get_watchdog_settings(db: Session) -> Dict[str, Any]:
    """
    DB의 system_config 테이블에서 Watchdog 설정을 조회하여 기본값과 병합 반환합니다.
    """
    settings = dict(DEFAULT_WATCHDOG_CONFIG)
    keys = list(DEFAULT_WATCHDOG_CONFIG.keys())

    configs = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()
    for cfg in configs:
        # JSONType/JSONB로 저장된 값 파싱
        val = cfg.value
        if isinstance(val, dict) and "value" in val:
            val = val["value"]
        settings[cfg.key] = val

    # 타입 캐스팅 보정
    try:
        settings["watchdog_enabled"] = bool(settings["watchdog_enabled"])
        settings["watchdog_fail_threshold"] = int(settings["watchdog_fail_threshold"])
        settings["watchdog_security_alert"] = bool(settings["watchdog_security_alert"])
        settings["watchdog_instruction_delay_minutes"] = int(settings["watchdog_instruction_delay_minutes"])
    except (ValueError, TypeError):
        pass

    return settings


def check_and_alert_task_failure(db: Session, failed_task_id: Optional[int] = None) -> bool:
    """
    [1. 워커 연속 실패 감시]
    최근 1시간 내 FAILED 태스크가 임계치(기본 3회)에 도달하면 관리자에게 L4 경보를 발행합니다.
    """
    cfg = get_watchdog_settings(db)
    if not cfg.get("watchdog_enabled", True):
        return False

    threshold = cfg.get("watchdog_fail_threshold", 3)
    one_hour_ago = datetime.now() - timedelta(hours=1)

    fail_count = db.query(func.count(SystemTask.id)).filter(
        and_(
            SystemTask.status == "FAILED",
            SystemTask.completed_at >= one_hour_ago
        )
    ).scalar() or 0

    if fail_count >= threshold:
        cooldown_key = "task_failure"
        if _is_in_cooldown(cooldown_key):
            logger.info(f"⏳ Watchdog: 태스크 실패 쿨다운 중 (누적: {fail_count}건)")
            return False

        _set_cooldown(cooldown_key)
        logger.warning(f"🚨 Watchdog: 태스크 연속 실패 임계치 도달 ({fail_count}/{threshold})! 관리자 경보 발송")

        task_id_info = f"작업 ID #{failed_task_id} 포함 " if failed_task_id else ""
        safe_notify(
            db=db,
            category="ALARM",
            title="🚨 [시스템 경보] 백그라운드 태스크 연속 실패 감지",
            message=f"{task_id_info}최근 1시간 내 총 {fail_count}건의 태스크가 영구 실패했습니다. 워커 큐를 즉시 점검하십시오.",
            target_groups=["admin"],
            level=4,
            link="/v1/admin/tasks"
        )
        return True

    return False


def check_and_alert_security_violation(db: Session, audit_log: AuditLog) -> bool:
    """
    [2. 보안 및 권한 침해 시도 감시]
    403 Forbidden 및 비정상 권한 침해 시도가 감사로그에 적재될 때 관리자에게 즉시 L4 경보를 발행합니다.
    (관리자의 정상적인 시스템 통제 및 세션 추방 행위는 침해가 아니므로 제외)
    """
    cfg = get_watchdog_settings(db)
    if not cfg.get("watchdog_enabled", True) or not cfg.get("watchdog_security_alert", True):
        return False

    # 📌 관리자의 정상적인 통제 행위 및 세션 강제 추방은 보안 침해 경보 대상에서 제외
    NORMAL_ACTIONS = {"SESSION_KICKED", "SESSION_REVOKED", "ADMIN_KICK", "PERM_CHANGED", "LOGIN_SUCCESS", "LOGOUT"}
    if audit_log.action in NORMAL_ACTIONS or (audit_log.metadata_payload and audit_log.metadata_payload.get("admin_id")):
        return False

    cooldown_key = f"security_{audit_log.app_id or 'unknown'}"
    if _is_in_cooldown(cooldown_key):
        return False

    _set_cooldown(cooldown_key)
    logger.warning(f"🛡️ Watchdog: 보안 침해 감지! 관리자 경보 발송 (Action: {audit_log.action})")

    safe_notify(
        db=db,
        category="ALARM",
        title="🛡️ [보안 경보] 비인가 접근 및 권한 침해 시도 감지",
        message=f"인가되지 않은 관리자 리소스 접근 시도가 감지되었습니다. (행위: {audit_log.action}, 대상: {audit_log.app_id})",
        target_groups=["admin"],
        level=4,
        link="/v1/admin/observability"
    )
    return True


def check_and_alert_instruction_delays(db: Session) -> bool:
    """
    [3. 현장 지시사항 미확인 지연 감시]
    지시사항 발행 후 지정 시간(기본 30분) 경과 후에도 미확인율이 50% 이상인 경우 경보를 발행합니다.
    """
    cfg = get_watchdog_settings(db)
    if not cfg.get("watchdog_enabled", True):
        return False

    delay_minutes = cfg.get("watchdog_instruction_delay_minutes", 30)
    delay_threshold = datetime.now() - timedelta(minutes=delay_minutes)
    twenty_four_hours_ago = datetime.now() - timedelta(hours=24)

    # 최근 24시간 내 발행되었고 최소 delay_minutes가 경과한 지시사항 조회
    delayed_instructions = db.query(MiniappItem).filter(
        and_(
            MiniappItem.category == "INSTRUCTION",
            MiniappItem.status == "PENDING",
            MiniappItem.created_at <= delay_threshold,
            MiniappItem.created_at >= twenty_four_hours_ago
        )
    ).all()

    if len(delayed_instructions) >= 3:
        cooldown_key = "instruction_delay"
        if _is_in_cooldown(cooldown_key):
            return False

        _set_cooldown(cooldown_key)
        logger.warning(f"⚠️ Watchdog: 긴급 지시사항 {len(delayed_instructions)}건 미확인 지연 감지!")

        safe_notify(
            db=db,
            category="ALARM",
            title="⚠️ [관제 경보] 현장 지시사항 미인지 지연 감지",
            message=f"발행 후 {delay_minutes}분이 경과했으나 미확인된 현장 지시사항이 {len(delayed_instructions)}건 있습니다. 현장 전달 상태를 확인하십시오.",
            target_groups=["admin"],
            level=4,
            link="/v1/admin/alerts"
        )
        return True

    return False


def run_watchdog_inspection(db: Session) -> Dict[str, Any]:
    """
    [자율 종합 감시 루틴]
    모든 이상 징후를 종합 점검하고 결과 리포트를 반환합니다.
    """
    res_task = check_and_alert_task_failure(db)
    res_inst = check_and_alert_instruction_delays(db)

    return {
        "inspected_at": datetime.now().isoformat(),
        "task_failure_alert_triggered": res_task,
        "instruction_delay_alert_triggered": res_inst,
        "status": "HEALTHY" if not (res_task or res_inst) else "ALERTED"
    }
