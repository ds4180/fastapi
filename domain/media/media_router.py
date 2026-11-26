"""
============================================================================
[미디어 자산 통합 라우터 (domain/media/media_router.py)]
============================================================================
- 비즈니스 로직은 media_service / media_explorer_service / media_policy_service로 분리하고,
  본 라우터는 HTTP 입출력, AppRegistry('media') 거버넌스 인가 가드, 감사로그 기록만 담당합니다.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from core.audit import safe_log_audit
from core.deps import require_app_permission
from database import get_db
from domain.media import media_service
from domain.media.media_explorer_service import (
    build_media_zip_stream,
    bulk_delete_media,
    create_media_folder,
    get_media_stats_summary,
    get_recent_media_by_tier,
    is_protected_root_folder as _is_protected_root_folder,
    list_media_directory,
    resolve_best_fallback_abs,
    resolve_secure_serve_response,
)
from domain.media.media_policy_service import (
    can_user_read_asset,
    check_is_media_admin,
    get_media_settings,
    update_media_settings,
    validate_upload_permission,
)
from domain.media.media_schema import (
    BulkActionRequest,
    FolderCreateRequest,
    GCRequest,
    MediaSettingsUpdate,
    PublishRequest,
)
from domain.system.task_service import enqueue_task
from domain.user.user_router import get_current_user
from models import MediaAsset, User

router = APIRouter(
    prefix="/media",
    tags=["Media System"],
)

# 🏛️ AppRegistry('media') 거버넌스 인가 가드
check_media_admin = require_app_permission("media", action="read")
check_media_admin_write = require_app_permission("media", action="write")


@router.get("/serve/{asset_id}")
async def media_secure_serve(
    asset_id: int,
    size: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """보안 Tier 미디어 서빙 — 동적 정책 권한 검증 후 Nginx X-Accel-Redirect 전달"""
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다.")

    if not can_user_read_asset(current_user, asset, db):
        raise HTTPException(status_code=403, detail="해당 미디어 자산 열람 권한이 없습니다.")

    redirect_path, content_type = resolve_secure_serve_response(db, asset, size=size)
    if not redirect_path:
        return RedirectResponse(url="/default-thumbnail.png")

    return Response(
        headers={
            "X-Accel-Redirect": redirect_path,
            "Content-Type": content_type,
        }
    )


@router.get("/admin/settings")
async def media_get_settings_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    탐색기 초기 구성 및 정책 설정 조회
    - 로그인 사용자는 업로드 제한·탐색기 기본값·탭 라벨 및 본인의 media 거버넌스 권한 플래그를 함께 수신합니다.
    """
    settings = get_media_settings(db)
    return {
        "settings": settings,
        "permissions": {
            "can_admin_read": check_is_media_admin(current_user, db, action="read"),
            "can_admin_write": check_is_media_admin(current_user, db, action="write"),
        },
    }


@router.put("/admin/settings")
async def media_update_settings_api(
    payload: MediaSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin_write),
):
    """미디어 자산 관리 동적 정책 설정 저장 (media 쓰기 관리자 전용)"""
    old_cfg, new_cfg = update_media_settings(db, payload.model_dump())

    diff_payload = [
        {"field": k, "from": old_cfg.get(k), "to": new_cfg.get(k)}
        for k in new_cfg
        if old_cfg.get(k) != new_cfg.get(k)
    ]
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="UPDATE_SETTINGS",
        title="미디어 관리 정책 설정 변경",
        user=current_user,
        severity="INFO",
        resource_type="system_config",
        resource_id="media_settings",
        diff_payload=diff_payload,
        message=f"미디어 정책 설정 {len(diff_payload)}개 항목을 갱신했습니다.",
    )
    return {"message": "미디어 정책 설정이 저장되었습니다.", "settings": new_cfg}


@router.get("/admin/stats")
async def media_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin),
):
    return get_media_stats_summary(db)


@router.get("/admin/recent")
async def media_admin_recent(
    limit: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin),
):
    return get_recent_media_by_tier(db, limit=limit)


@router.post("/upload")
async def media_upload(
    app_id: str = "general",
    target_id: Optional[str] = None,
    access_level: Optional[str] = None,
    sub_path: Optional[str] = None,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """통합 파일 업로드 엔드포인트 (동적 용량·확장자·권한 검증 포함)"""
    settings = get_media_settings(db)
    target_tier = (
        access_level or media_service.media_get_access_level(current_user, app_id, db=db)
    ).upper()
    clean_sub_path = (sub_path or "").strip("/")

    validate_upload_permission(current_user, db, target_tier, clean_sub_path, settings=settings)

    return await media_service.media_process_upload(
        db=db,
        user=current_user,
        files=files,
        app_id=app_id,
        target_id=target_id,
        access_level=target_tier,
        sub_path=sub_path,
    )


@router.post("/publish")
async def media_publish(
    req: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """개인 보관함(PRIVATE) 자산을 서비스 영역(PUBLIC/PROTECTED)으로 배포 복사"""
    if not req.asset_ids:
        raise HTTPException(status_code=400, detail="선택된 파일이 없습니다.")
    target_tier = (req.access_level or "PUBLIC").upper()
    is_admin = check_is_media_admin(current_user, db, action="write")
    if not is_admin and target_tier not in ("PUBLIC", "PROTECTED"):
        raise HTTPException(status_code=403, detail="서비스 배포는 PUBLIC 또는 PROTECTED 영역으로만 가능합니다.")

    published = media_service.media_publish_assets(
        db=db,
        user=current_user,
        asset_ids=req.asset_ids,
        app_id=req.app_id,
        target_id=req.target_id,
        access_level=target_tier,
        sub_path=req.sub_path,
    )
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="PUBLISH",
        title="미디어 자산 서비스 배포 (Publish)",
        user=current_user,
        severity="INFO",
        resource_type="media_asset",
        resource_id=str(req.asset_ids),
        message=f"개인 자산 {len(published)}건을 [{target_tier}] 영역으로 배포 복사했습니다.",
    )
    return published


@router.get("/admin/list")
async def media_admin_list(
    tier: str = "PUBLIC",
    sub_path: str = "",
    recursive: bool = True,
    show_hidden: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_media_directory(
        db=db,
        current_user=current_user,
        tier=tier,
        sub_path=sub_path,
        recursive=recursive,
        show_hidden=show_hidden,
    )


@router.post("/admin/folder/create")
async def media_admin_create_folder(
    req: FolderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder_full_path = create_media_folder(
        db=db,
        current_user=current_user,
        tier=req.tier,
        sub_path=req.sub_path,
        folder_name=req.folder_name,
    )
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="CREATE_FOLDER",
        title="미디어 폴더 생성",
        user=current_user,
        severity="INFO",
        resource_type="folder",
        resource_id=folder_full_path,
        message=f"[{req.tier.upper()}] /{folder_full_path} 폴더를 생성했습니다.",
    )
    return {"message": "Folder created", "path": folder_full_path}


@router.post("/admin/zip-download")
async def media_admin_zip_download(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    zip_buffer, added_count = build_media_zip_stream(
        db=db,
        current_user=current_user,
        tier=req.tier,
        asset_ids=req.asset_ids,
        folder_paths=req.folder_paths,
    )
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="ACCESS",
        action="ZIP_DOWNLOAD",
        title="미디어 자산 일괄 ZIP 다운로드",
        user=current_user,
        severity="INFO",
        resource_type="media_asset",
        resource_id=f"assets:{len(req.asset_ids)},folders:{len(req.folder_paths)}",
        message=f"총 {added_count}건의 미디어 자산을 ZIP 아카이브로 다운로드했습니다.",
    )
    filename = f"media_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/backup")
async def media_admin_backup(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin_write),
):
    if req.folder_paths:
        raise HTTPException(status_code=400, detail="폴더 백업은 현재 지원되지 않습니다. 파일을 선택해 주세요.")

    task = enqueue_task(
        db=db,
        task_type="MEDIA_BACKUP",
        payload={"asset_ids": req.asset_ids, "target_user_id": current_user.id},
        priority=3,
    )
    db.commit()
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="ACCESS",
        action="BACKUP",
        title="미디어 자산 백업 예약",
        user=current_user,
        severity="INFO",
        resource_type="media_asset",
        resource_id=str(req.asset_ids),
        message=f"미디어 자산 {len(req.asset_ids)}건 백업 태스크(ID: {task.id})를 예약했습니다.",
    )
    return {"message": "백업 작업이 예약되었습니다.", "task_id": task.id}


@router.post("/admin/bulk-delete")
async def media_admin_bulk_delete(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submitted_count = bulk_delete_media(
        db=db,
        current_user=current_user,
        tier=req.tier,
        asset_ids=req.asset_ids,
        folder_paths=req.folder_paths,
    )
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="DELETE",
        title="미디어 자산/폴더 일괄 삭제(격리)",
        user=current_user,
        severity="WARN",
        resource_type="media_asset",
        resource_id=f"assets:{len(req.asset_ids)},folders:{len(req.folder_paths)}",
        message=f"총 {submitted_count}건의 미디어 자산/폴더를 삭제(격리) 처리했습니다.",
    )
    return {"message": f"{submitted_count}건의 삭제 작업이 처리되었습니다."}


@router.post("/admin/gc")
async def media_admin_run_gc(
    req: GCRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin_write),
):
    settings = get_media_settings(db)
    indices = req.indices if req.indices else settings.get("default_gc_indices", [1, 2, 3, 4, 5, 6])
    task = enqueue_task(
        db=db,
        task_type="MEDIA_GC",
        payload={"indices": indices},
        scheduled_at=req.scheduled_at,
        unique_key=f"gc-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        priority=9,
    )
    db.commit()
    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="GC",
        title="미디어 스토리지 GC 실행 예약",
        user=current_user,
        severity="WARN",
        resource_type="system_task",
        resource_id=str(task.id),
        message=f"미디어 시스템 가비지 컬렉션(GC: {indices}) 작업을 예약했습니다. (Task ID: {task.id})",
    )
    return {"message": "시스템 정리(GC) 작업이 예약되었습니다.", "task_id": task.id}


@router.post("/delete/{asset_id}")
async def media_admin_delete(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.is_deleted == False).first()
    if not asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 이미 삭제되었습니다.")

    is_admin = check_is_media_admin(current_user, db, action="write")
    if asset.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="본인의 파일만 삭제할 수 있습니다.")

    asset_name = asset.original_name
    if not media_service.delete_asset(db, asset_id):
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 삭제에 실패했습니다.")

    safe_log_audit(
        db=db,
        app_id="media",
        log_type="CHANGE",
        action="DELETE",
        title="미디어 자산 단일 삭제(격리)",
        user=current_user,
        severity="WARN",
        resource_type="media_asset",
        resource_id=str(asset_id),
        message=f"미디어 자산 [{asset_id}] {asset_name}을(를) 삭제(격리) 처리했습니다.",
    )
    return {"message": "Successfully deleted"}
