"""
============================================================================
[시스템 데이터 보존 및 가비지 컬렉션 엔진 (domain/system/retention_service.py)]
============================================================================

💡 이 파일의 역할:
Redis 인메모리 캐시 키의 수명(TTL)을 강제하고,
PostgreSQL DB에 무기한 누적되는 감사로그, 세션 이력, 완료 태스크를
보존 정책(Retention Policy)에 따라 자율 정리(GC)하여 메모리 OOM과 디스크 고갈을 방지합니다.
"""

from __future__ import annotations
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.system import SystemConfig, SystemTask
from models.user import UserSession
from models.audit import AuditLog
from core.audit import safe_log_audit

logger = logging.getLogger("system.retention")

# ⚙️ 기본 보존 주기 규격 (STD-SYS-009)
DEFAULT_RETENTION_CONFIG: Dict[str, Any] = {
    "retention_audit_log_days": 180,        # 감사로그 보존 기간 (일)
    "retention_system_task_days": 30,       # 완료/실패 태스크 보존 기간 (일)
    "retention_session_history_days": 60,   # 만료 세션 이력 보존 기간 (일)
    "retention_redis_dynamic_hours": 48     # 동적 타겟 그룹 Redis 만료 기한 (시간)
}


def get_retention_settings(db: Session) -> Dict[str, Any]:
    """
    DB의 system_config 테이블에서 데이터 보존 설정을 조회하여 기본값과 병합 반환합니다.
    """
    settings = dict(DEFAULT_RETENTION_CONFIG)
    keys = list(DEFAULT_RETENTION_CONFIG.keys())

    configs = db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).all()
    for cfg in configs:
        val = cfg.value
        if isinstance(val, dict) and "value" in val:
            val = val["value"]
        settings[cfg.key] = val

    # 정수형 캐스팅 보정
    for k in settings:
        try:
            settings[k] = int(settings[k])
        except (ValueError, TypeError):
            settings[k] = DEFAULT_RETENTION_CONFIG[k]

    return settings


def clean_redis_keys(rd, dynamic_ttl_hours: int = 48) -> Dict[str, int]:
    """
    [Redis 인메모리 수명 관리 및 고아 키 수거]
    1. TTL이 없는(-1) 동적 그룹 키에 TTL 강제 주입.
    2. 메타데이터에 등록되지 않은 고아 키 정리.
    """
    if not rd:
        return {"ttl_enforced": 0, "orphans_removed": 0}

    ttl_enforced = 0
    orphans_removed = 0
    dynamic_ttl_seconds = dynamic_ttl_hours * 3600

    try:
        # 1. 메타데이터 조회
        metas = rd.hgetall("group:metadata") or {}
        registered_group_names = set()
        dynamic_group_names = set()

        for name_bytes, meta_str in metas.items():
            name = name_bytes.decode("utf-8") if isinstance(name_bytes, bytes) else str(name_bytes)
            registered_group_names.add(name)
            try:
                meta = json.loads(meta_str)
                if meta.get("type") == "dynamic" or "today" in name or "dispatch" in name:
                    dynamic_group_names.add(name)
            except Exception:
                pass

        # 2. Redis 내 group:data:* 키 비블로킹 스캔 (싱글 스레드 블로킹을 유발하는 KEYS 대신 SCAN 사용)
        key_iter = (
            rd.scan_iter(match="group:data:*", count=100)
            if hasattr(rd, "scan_iter")
            else rd.keys("group:data:*")
        )
        for k_bytes in key_iter:
            k = k_bytes.decode("utf-8") if isinstance(k_bytes, bytes) else str(k_bytes)
            group_name = k.replace("group:data:", "")

            # 2-1. 메타데이터에 없는 고아 키는 삭제
            if group_name not in registered_group_names:
                rd.delete(k)
                orphans_removed += 1
                logger.info(f"🧹 [Redis GC] 고아 키 삭제: {k}")
                continue

            # 2-2. 동적 그룹 키인데 TTL이 -1(무기한)이면 TTL 강제 부여
            if group_name in dynamic_group_names:
                current_ttl = rd.ttl(k)
                if current_ttl == -1:
                    rd.expire(k, dynamic_ttl_seconds)
                    ttl_enforced += 1
                    logger.info(f"⏳ [Redis GC] 만료 기한 강제 부여: {k} (TTL: {dynamic_ttl_hours}h)")

    except Exception as e:
        logger.warning(f"⚠️ [Redis GC] 정리 중 오류 발생: {e}")

    return {
        "ttl_enforced": ttl_enforced,
        "orphans_removed": orphans_removed
    }


def run_data_retention_gc(db: Session, rd=None) -> Dict[str, Any]:
    """
    [자율 종합 데이터 보존 및 가비지 컬렉션(GC) 실행기]
    - Redis TTL 강제 및 고아 키 제거
    - PostgreSQL 만료 태스크 / 세션 이력 / 감사로그 삭제
    - 작업 이력 감사로그 보존
    """
    cfg = get_retention_settings(db)
    now = datetime.now()

    # 0. 비활동 만료 기간(SESSION_EXPIRE_DAYS)을 초과한 방치 ACTIVE 세션을 먼저 EXPIRED로 전환
    try:
        from core.session import sync_expired_sessions
        sync_expired_sessions(db)
    except Exception as sync_err:
        logger.warning(f"⚠️ [Retention GC] 만료 세션 사전 동기화 오류 (무시됨): {sync_err}")

    # 1. Redis 인메모리 GC
    redis_res = clean_redis_keys(rd, dynamic_ttl_hours=cfg["retention_redis_dynamic_hours"])

    # 2. 백그라운드 태스크 로그 정리 (부모-자식 parent_id 사슬 FK 충돌 방어 및 CANCELLED 포함)
    task_threshold = now - timedelta(days=cfg["retention_system_task_days"])
    expired_task_cond = and_(
        SystemTask.status.in_(["SUCCESS", "FAILED", "CANCELLED"]),
        or_(
            and_(SystemTask.completed_at.isnot(None), SystemTask.completed_at <= task_threshold),
            and_(SystemTask.completed_at.is_(None), SystemTask.created_at <= task_threshold),
        ),
    )
    expired_task_ids_subq = db.query(SystemTask.id).filter(expired_task_cond).subquery()
    # 삭제 대상 부모 행을 참조하는 생존 자식 행의 parent_id를 먼저 NULL 해제 (DB FK 안전 보강)
    db.query(SystemTask).filter(
        SystemTask.parent_id.in_(db.query(expired_task_ids_subq.c.id))
    ).update({SystemTask.parent_id: None}, synchronize_session=False)

    deleted_tasks = db.query(SystemTask).filter(expired_task_cond).delete(synchronize_session=False)

    # 3. 종료·추방·자연만료(EXPIRED 포함) 세션 이력 정리
    session_threshold = now - timedelta(days=cfg["retention_session_history_days"])
    deleted_sessions = db.query(UserSession).filter(
        and_(
            UserSession.status.in_(["LOGOUT", "KICKED_OUT", "EXPIRED"]),
            or_(
                and_(UserSession.logout_at.isnot(None), UserSession.logout_at <= session_threshold),
                and_(UserSession.logout_at.is_(None), UserSession.login_at <= session_threshold),
            ),
        )
    ).delete(synchronize_session=False)

    # 4. 감사로그 정리
    audit_threshold = now - timedelta(days=cfg["retention_audit_log_days"])
    deleted_audits = db.query(AuditLog).filter(
        AuditLog.created_at <= audit_threshold
    ).delete(synchronize_session=False)

    db.commit()

    report = {
        "status": "SUCCESS",
        "executed_at": now.isoformat(),
        "deleted_tasks": deleted_tasks,
        "deleted_sessions": deleted_sessions,
        "deleted_audit_logs": deleted_audits,
        "redis_ttl_enforced": redis_res["ttl_enforced"],
        "redis_orphans_removed": redis_res["orphans_removed"]
    }

    logger.info(f"✨ [Data Retention GC 완료]: {report}")

    # 5. 감사로그에 GC 수행 결과 기록
    safe_log_audit(
        db=db,
        app_id="system",
        log_type="CHANGE",
        severity="INFO",
        action="DATA_RETENTION_GC",
        title=f"시스템 데이터 정기 가비지 컬렉션(GC) 수행",
        metadata=report,
        commit=True
    )

    return report
