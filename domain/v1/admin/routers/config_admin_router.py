from typing import List
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import require_app_permission
from database import get_db
from domain.v1.admin import admin_schema
from models import SystemConfig, User

router = APIRouter()

check_config_admin_read = require_app_permission("config", action="read")
check_config_admin_write = require_app_permission("config", action="write")
check_config_admin = check_config_admin_read  # 하위 호환 보존


@router.get("/config", response_model=List[admin_schema.SystemConfigSchema])
def get_all_configs(db: Session = Depends(get_db), admin: User = Depends(check_config_admin_read)):
    """전사 시스템 환경 설정 조회 (config 앱 읽기 권한 이상)"""
    return db.query(SystemConfig).order_by(SystemConfig.key).all()


@router.put("/config/batch")
def update_configs_batch(
    payload: dict = Body(..., description="키-값 딕셔너리"),
    db: Session = Depends(get_db),
    admin: User = Depends(check_config_admin_write),
):
    """
    [전사 시스템 환경 설정 일괄 저장]
    단일 트랜잭션으로 여러 설정을 안전하게 원자적 저장하고, 변경 감사로그를 자동 기록합니다.
    """
    changed_diff = {}
    for key, new_val in payload.items():
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        old_val = config.value if config else None
        if not config:
            config = SystemConfig(key=key, value=new_val)
            db.add(config)
            changed_diff[key] = {"old": None, "new": new_val}
        else:
            if config.value != new_val:
                changed_diff[key] = {"old": old_val, "new": new_val}
                config.value = new_val

    if changed_diff:
        db.commit()
        safe_log_audit(
            db=db,
            app_id="config",
            log_type="CHANGE",
            severity="INFO",
            action="CONFIG_BATCH_UPDATED",
            title=f"관리자({admin.username})에 의한 시스템 환경설정 {len(changed_diff)}건 일괄 변경",
            user=admin,
            resource_type="system_config",
            message=f"환경설정 항목 {list(changed_diff.keys())} 변경 완료",
            diff_payload=[{"field": k, "from": str(v["old"]), "to": str(v["new"])} for k, v in changed_diff.items()],
            metadata={"admin_id": admin.id, "changes": changed_diff},
        )

    return {"message": "success", "updated_count": len(changed_diff), "keys": list(changed_diff.keys())}


@router.put("/config/{key}", response_model=admin_schema.SystemConfigSchema)
def update_config(
    key: str,
    payload: admin_schema.SystemConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_config_admin_write),
):
    """단일 시스템 환경 설정 갱신 (하위 호환)"""
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    old_val = config.value if config else None
    if not config:
        config = SystemConfig(key=key, value=payload.value, description=payload.description)
        db.add(config)
    else:
        config.value = payload.value
        if payload.description is not None:
            config.description = payload.description
    db.commit()
    db.refresh(config)

    safe_log_audit(
        db=db,
        app_id="config",
        log_type="CHANGE",
        severity="INFO",
        action="CONFIG_UPDATED",
        title=f"관리자({admin.username})에 의한 환경설정 '{key}' 변경",
        user=admin,
        resource_type="system_config",
        resource_id=key,
        message=f"설정 '{key}' 값이 변경되었습니다: {old_val} -> {payload.value}",
        diff_payload=[{"field": key, "from": str(old_val), "to": str(payload.value)}],
        metadata={"admin_id": admin.id, "key": key, "old_value": old_val, "new_value": payload.value},
    )

    return config


@router.get("/config/public")
def get_public_configs(db: Session = Depends(get_db)):
    configs = db.query(SystemConfig).all()
    return {c.key: c.value for c in configs}


@router.post("/system/gc/run")
def run_manual_gc(db: Session = Depends(get_db), admin: User = Depends(check_config_admin_write)):
    """[관리자 수동 즉시 실행] 데이터 보존 기간 초과 이력 및 Redis 메모리 가비지 컬렉션(GC) (STD-SYS-009)"""
    from domain.system.retention_service import run_data_retention_gc
    from redis_config import rd

    gc_result = run_data_retention_gc(db, rd)

    safe_log_audit(
        db=db,
        app_id="config",
        log_type="SECURITY",
        severity="WARN",
        action="MANUAL_GC_TRIGGERED",
        title=f"관리자({admin.username})에 의한 전사 수동 가비지 컬렉션(GC) 즉시 실행",
        user=admin,
        resource_type="system_gc",
        message=(
            f"수동 GC 완료: 태스크 {gc_result.get('deleted_tasks', 0)}건, "
            f"세션 {gc_result.get('deleted_sessions', 0)}건, "
            f"감사로그 {gc_result.get('deleted_audit_logs', 0)}건 정리, "
            f"Redis TTL {gc_result.get('redis_ttl_enforced', 0)}건 주입, "
            f"고아키 {gc_result.get('redis_orphans_removed', 0)}건 수거"
        ),
        metadata={"admin_id": admin.id, "gc_result": gc_result},
    )

    return gc_result
