from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import get_current_user, require_app_permission
from database import get_db
from domain.system.app_service import migrate_boards_to_board
from domain.v1.admin import admin_schema
from models import AppRegistry, User

router = APIRouter()

check_app_admin = require_app_permission("apps")


@router.get("/apps", response_model=List[admin_schema.AppRegistrySchema])
def get_all_apps(db: Session = Depends(get_db), admin: User = Depends(check_app_admin)):
    """시스템에 등록된 모든 App 엔진 목록 조회 (관리자용)"""
    migrate_boards_to_board(db)
    return db.query(AppRegistry).order_by(AppRegistry.app_id).all()


@router.get("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def get_app_detail(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    [특정 앱의 메타데이터 및 권한 정보 상세 조회]
    - SSR 라우트 가드(/v1/admin/+layout.server.ts)에서 Lv.8 이하 로그인 사용자도
      진입 대상 앱의 4단계 권한 규칙(allow/deny_groups, min_read_rank)을 판별할 수 있어야 하므로
      get_current_user를 요구합니다.
    - 하위 호환을 위해 'admin_' 접두사가 붙은 app_id 조회 시 접두사를 제거한 식별자도 fallback 탐색합니다.
    """
    migrate_boards_to_board(db)
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app and app_id.startswith("admin_"):
        db_app = db.query(AppRegistry).filter(
            AppRegistry.app_id == app_id.removeprefix("admin_")
        ).first()
    if not db_app and app_id in ("board", "boards"):
        alt_id = "boards" if app_id == "board" else "board"
        db_app = db.query(AppRegistry).filter(AppRegistry.app_id == alt_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="등록되지 않은 앱 엔진입니다.")
    return db_app


@router.post("/apps", response_model=admin_schema.AppRegistrySchema)
def create_app_registry(
    app_in: admin_schema.AppRegistryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_app_admin),
):
    """
    [신규 App 엔진 및 메타데이터 등록]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 중복 식별자(app_id) 방어 및 Pydantic 엄격 검증(app_type 4대 분류, frontend_route 포맷)
    - 📜 최고 관리자 등록 행위(APP_REGISTERED) 보안 감사로그(AuditLog) 영구 보존
    """
    existing = db.query(AppRegistry).filter(AppRegistry.app_id == app_in.app_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 앱 식별자입니다.")

    payload = app_in.dict()

    db_app = AppRegistry(**payload)
    db.add(db_app)
    db.commit()
    db.refresh(db_app)

    safe_log_audit(
        db=db,
        app_id="apps",
        log_type="SECURITY",
        action="APP_REGISTERED",
        title=f"신규 앱 엔진 등록: {db_app.title or db_app.name} ({db_app.app_id})",
        user=admin,
        resource_type="app_registry",
        resource_id=db_app.app_id,
        message=f"유형: {db_app.app_type}, 진입로: {db_app.frontend_route}, 랭크: R{db_app.min_read_rank}/W{db_app.min_write_rank}",
        metadata={
            "app_id": db_app.app_id,
            "app_type": db_app.app_type,
            "min_read_rank": db_app.min_read_rank,
            "min_write_rank": db_app.min_write_rank,
            "allow_groups": db_app.allow_groups,
            "deny_groups": db_app.deny_groups,
        },
    )

    return db_app


@router.patch("/apps/{app_id}", response_model=admin_schema.AppRegistrySchema)
def update_app_registry(
    app_id: str,
    app_in: admin_schema.AppRegistryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_app_admin),
):
    """
    [App 엔진 메타데이터 수정 (권한, 경로, 자치관리자 등)]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 🚨 SYSTEM 필수 앱 보호: app_type 변경 시도 및 is_active=False 비활성화 원천 차단 (403)
    - 📜 변경 전/후 필드 차이점(Diff-Patch) 자동 추적 및 보안/시스템 감사로그(AuditLog) 영구 보존
    """
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")

    update_data = app_in.dict(exclude_unset=True)

    # 🚨 [SYSTEM 필수 관제 앱 철벽 방어선]
    if db_app.app_type == "SYSTEM":
        if "app_type" in update_data and update_data["app_type"] != "SYSTEM":
            raise HTTPException(
                status_code=403,
                detail="SYSTEM 앱의 유형(app_type)은 시스템 필수 규격이므로 변경할 수 없습니다.",
            )
        if "is_active" in update_data and update_data["is_active"] is False:
            raise HTTPException(
                status_code=403,
                detail="SYSTEM 앱은 시스템 필수 관제 앱이므로 비활성화할 수 없습니다.",
            )

    diff_list = []
    for key, value in update_data.items():
        old_val = getattr(db_app, key, None)
        if old_val != value:
            diff_list.append(
                {
                    "field": key,
                    "from": old_val,
                    "to": value,
                }
            )
            setattr(db_app, key, value)

    db.commit()
    db.refresh(db_app)

    if diff_list:
        is_security_change = any(
            f["field"]
            in ["min_read_rank", "min_write_rank", "allow_groups", "deny_groups", "is_active", "app_type"]
            for f in diff_list
        )
        safe_log_audit(
            db=db,
            app_id="apps",
            log_type="SECURITY" if is_security_change else "SYSTEM",
            action="APP_UPDATED",
            title=f"앱 엔진 메타데이터 수정: {db_app.title or db_app.name} ({db_app.app_id})",
            user=admin,
            resource_type="app_registry",
            resource_id=db_app.app_id,
            message=f"{len(diff_list)}개 항목 변경 완료: " + ", ".join([d["field"] for d in diff_list]),
            diff_payload=diff_list,
            metadata={"updated_fields": list(update_data.keys())},
        )

    return db_app


@router.delete("/apps/{app_id}")
def delete_app(app_id: str, db: Session = Depends(get_db), admin: User = Depends(check_app_admin)):
    """
    [앱 등록 해제 및 제거]
    - 인가 가드: admin_apps 전용 인가 가드(check_app_admin, Rank 9)
    - 🚨 SYSTEM 앱은 시스템 필수 관제 앱이므로 삭제 영구 차단 (403)
    - 📜 최고 관리자 앱 삭제 행위(APP_DELETED) 보안 감사로그(AuditLog, WARN) 영구 보존
    """
    db_app = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not db_app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    if db_app.app_type == "SYSTEM":
        raise HTTPException(status_code=403, detail="SYSTEM 앱은 시스템 필수 관제 앱이므로 삭제할 수 없습니다.")

    app_name = db_app.title or db_app.name
    app_type = db_app.app_type

    db.delete(db_app)
    db.commit()

    safe_log_audit(
        db=db,
        app_id="apps",
        log_type="SECURITY",
        action="APP_DELETED",
        title=f"앱 엔진 삭제 완료: {app_name} ({app_id})",
        user=admin,
        severity="WARN",
        resource_type="app_registry",
        resource_id=app_id,
        message=f"유형: {app_type} 앱이 시스템에서 영구 삭제되었습니다.",
        metadata={"app_id": app_id, "app_type": app_type},
    )

    return {"message": "success"}
