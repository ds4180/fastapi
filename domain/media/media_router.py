from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, not_
from typing import List, Optional
from database import get_db
from domain.user.user_router import get_current_user
from domain.media import media_service, media_config
from core.deps import require_app_permission
from core.permission import ROOT_RANK, get_user_rank, can_access_app
from core.audit import safe_log_audit
from models import User, MediaAsset, AppRegistry
import os
import shutil
import io
import zipfile
from datetime import datetime
from fastapi.responses import StreamingResponse, RedirectResponse
from pydantic import BaseModel

router = APIRouter(
    prefix="/media",
    tags=["Media System"]
)

# 🏛️ AppRegistry 거버넌스 연동 미디어 관리 권한 가드
check_media_admin = require_app_permission("media", action="read")
check_media_admin_write = require_app_permission("media", action="write")


def check_is_media_admin(user: User, db: Session, action: str = "read") -> bool:
    """사용자가 media 시스템 앱 관리자 권한을 보유하고 있는지 4단계 거버넌스로 검증"""
    if get_user_rank(user) == ROOT_RANK:
        return True
    app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "media").first()
    if not app_meta:
        # 하위 호환 폴백 (legacy admin_media)
        app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "admin_media").first()
    if not app_meta:
        return user.rank() >= 4
    return can_access_app(user, app_meta, action=action)

class FolderCreateRequest(BaseModel):
    tier: str
    sub_path: str
    folder_name: str

class BulkActionRequest(BaseModel):
    asset_ids: List[int] = []
    folder_paths: List[str] = [] 
    tier: str = "PUBLIC"

class PublishRequest(BaseModel):
    asset_ids: List[int]
    app_id: str = "general"
    target_id: Optional[str] = None
    access_level: str = "PUBLIC"
    sub_path: Optional[str] = None

class GCRequest(BaseModel):
    indices: List[int] = [1, 2, 3, 4, 5]
    scheduled_at: Optional[datetime] = None


def _is_own_private_path(user: User, tier: str, sub_path: str) -> bool:
    """사용자가 본인의 개인 폴더(PRIVATE/USERS/{user.id})에 접근 중인지 검증"""
    if tier.upper() != "PRIVATE":
        return False
    clean = sub_path.strip("/")
    user_root = f"USERS/{user.id}"
    return clean == user_root or clean.startswith(f"{user_root}/")


def _validate_safe_path(target_dir: str):
    """Path Traversal(../)을 통한 MEDIA_ROOT 외부 경로 이탈 차단"""
    real_root = os.path.realpath(media_config.MEDIA_ROOT)
    real_target = os.path.realpath(target_dir)
    if not (real_target == real_root or real_target.startswith(real_root + os.sep)):
        raise HTTPException(status_code=400, detail="Invalid path (Path traversal blocked)")

# [v3.2] 보안 미디어 서빙 (X-Accel-Redirect)
TIER_INTERNAL_MAP = {
    "PROTECTED": "/PROTECTED/",
    "PRIVATE": "/PRIVATE/",
    "SYSTEM": "/SYSTEM/",
}

@router.get("/serve/{asset_id}")
async def media_secure_serve(
    asset_id: int,
    size: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """보안 Tier 미디어 서빙 - 권한 검증 후 Nginx X-Accel-Redirect로 전달"""
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # 권한 검증
    if asset.access_level == "PRIVATE":
        if asset.user_id != current_user.id and current_user.rank() < 4:
            raise HTTPException(status_code=403, detail="Permission denied")
    elif asset.access_level in ["PROTECTED", "SYSTEM"]:
        if current_user.rank() < 2:
            raise HTTPException(status_code=403, detail="Permission denied")

    # 썸네일 요청 처리
    target_rel_path = asset.file_path
    if not size and asset.category == "image":
        # [v3.5] 원본 직접 요청 시 원본 부재(복제본 또는 60일 경과 파기) 시 고화질 썸네일(LG)로 안전 폴백
        orig_abs_path = os.path.join(media_config.MEDIA_ROOT, asset.file_path)
        if (asset.meta_info and asset.meta_info.get("has_original") is False) or not os.path.exists(orig_abs_path):
            base_name = os.path.basename(asset.file_path)
            unique_id = base_name.replace(media_config.PREFIX['IMAGE'], "").split('.')[0]
            dir_name = os.path.dirname(asset.file_path)
            lg_found = False
            for fallback_size in ["LG", "MD", "SM"]:
                fallback_name = f"{media_config.PREFIX['THUMB']}{unique_id}_{fallback_size}.WEBP"
                fallback_rel = os.path.join(dir_name, media_config.THUMB_FOLDER_NAME, fallback_name).replace("\\", "/")
                fallback_abs = os.path.join(media_config.MEDIA_ROOT, fallback_rel)
                if os.path.exists(fallback_abs):
                    target_rel_path = fallback_rel
                    lg_found = True
                    break
            if not lg_found:
                return RedirectResponse(url="/default-thumbnail.png")

    elif size and size.upper() in ["SM", "MD", "LG"]:
        size_upper = size.upper()
        
        # [v3.2] Task Worker 네이밍 규칙(UUID 기반)으로 수정
        base_name = os.path.basename(asset.file_path)
        unique_id = base_name.replace(media_config.PREFIX['IMAGE'], "").split('.')[0]
        thumb_name = f"{media_config.PREFIX['THUMB']}{unique_id}_{size_upper}.WEBP"
        
        # 썸네일 경로 계산 (원본 파일 위치 기준)
        dir_name = os.path.dirname(asset.file_path)
        thumb_rel_path = os.path.join(dir_name, media_config.THUMB_FOLDER_NAME, thumb_name).replace("\\", "/")
        thumb_abs_path = os.path.join(media_config.MEDIA_ROOT, thumb_rel_path)
        
        if os.path.exists(thumb_abs_path):
            target_rel_path = thumb_rel_path
        else:
            # 1. 레거시 썸네일 경로 호환 탐색
            legacy_found = False
            if asset.meta_info and isinstance(asset.meta_info.get("thumbs"), dict):
                saved_thumb = asset.meta_info["thumbs"].get(size.lower()) or asset.meta_info["thumbs"].get(size_upper)
                if saved_thumb:
                    saved_abs = os.path.join(media_config.MEDIA_ROOT, saved_thumb)
                    if os.path.exists(saved_abs):
                        target_rel_path = saved_thumb
                        legacy_found = True
            
            if not legacy_found:
                legacy_thumb_name = f"{unique_id}_{size.lower()}.webp"
                legacy_rel_path = os.path.join(dir_name, "thumbnails", legacy_thumb_name).replace("\\", "/")
                legacy_abs = os.path.join(media_config.MEDIA_ROOT, legacy_rel_path)
                if os.path.exists(legacy_abs):
                    target_rel_path = legacy_rel_path
                    legacy_found = True

            if not legacy_found:
                # [안전 가드 원칙]: 이미 삭제된 자산(is_deleted=True)이거나 디스크에 원본 파일이 없으면
                # 절대로 비동기 큐(THUMB_GEN)를 발행하지 않고 기본 이미지만 반환하여 큐 오염 방지
                orig_abs_path = os.path.join(media_config.MEDIA_ROOT, asset.file_path)
                if asset.is_deleted or not os.path.exists(orig_abs_path):
                    return RedirectResponse(url="/default-thumbnail.png")

                # 원본 파일이 실제로 디스크에 존재하는 정상 활성 자산만 비동기 썸네일 생성 예약
                from domain.system.task_service import enqueue_task
                enqueue_task(db, "THUMB_GEN", {"asset_id": asset.id}, priority=2, unique_key=f"thumb-gen-{asset.id}")
                db.commit()
                
                # [v3.2] 기본 이미지 반환
                return RedirectResponse(url="/default-thumbnail.png")

    internal_prefix = TIER_INTERNAL_MAP.get(asset.access_level, "/PUBLIC/")
    
    # [v3.2] 실제 파일 경로에서 티어명(첫 번째 경로) 제외하고 전달
    # 예: PRIVATE/IMAGE/2026/... -> IMAGE/2026/...
    parts = target_rel_path.split("/")
    if parts[0].upper() in media_config.MEDIA_TIERS:
        path_without_tier = "/".join(parts[1:])
    else:
        path_without_tier = target_rel_path

    redirect_path = f"{internal_prefix}{path_without_tier}"

    # [v3.5] 실제 서빙되는 파일(썸네일 등)의 확장자에 맞추어 Content-Type 안전 동기화
    ext = target_rel_path.split(".")[-1].lower()
    if ext == "webp":
        content_type = "image/webp"
    elif ext in ["jpg", "jpeg"]:
        content_type = "image/jpeg"
    elif ext == "png":
        content_type = "image/png"
    elif ext == "gif":
        content_type = "image/gif"
    elif ext == "svg":
        content_type = "image/svg+xml"
    elif ext == "pdf":
        content_type = "application/pdf"
    else:
        content_type = asset.mime_type or "application/octet-stream"

    return Response(
        headers={
            "X-Accel-Redirect": redirect_path,
            "Content-Type": content_type
        }
    )

@router.get("/admin/stats")
async def media_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin)
):
    total_count = db.query(func.count(MediaAsset.id)).filter(MediaAsset.is_deleted == False).scalar()
    total_size = db.query(func.sum(MediaAsset.file_size)).filter(MediaAsset.is_deleted == False).scalar() or 0
    
    tier_stats = db.query(
        MediaAsset.access_level,
        func.count(MediaAsset.id),
        func.sum(MediaAsset.file_size)
    ).filter(MediaAsset.is_deleted == False).group_by(MediaAsset.access_level).all()
    
    tier_summary = { row[0]: {"count": row[1], "size": row[2] or 0} for row in tier_stats }
    
    # [v3.2] 물리적 파일 워킹 제거 (성능 병목 지점) - DB 통계로 대체
    # folder_summary = {} ... 제거
    
    return {
        "total_count": total_count,
        "total_size_bytes": total_size,
        "tier_summary": tier_summary,
        "folder_physical_summary": {} 
    }

@router.get("/admin/recent")
async def media_admin_recent(
    limit: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin)
):
    
    recent = {}
    for tier in ["PUBLIC", "PROTECTED", "PRIVATE", "SYSTEM"]:
        recent[tier.lower()] = db.query(MediaAsset).filter(
            MediaAsset.access_level == tier,
            MediaAsset.is_deleted == False
        ).order_by(desc(MediaAsset.created_at)).limit(limit).all()
        
    return recent

@router.post("/upload")
async def media_upload(
    app_id: str = "general",
    target_id: str = None,
    access_level: str = None,
    sub_path: str = None,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[v3.3] 통합 파일 업로드 엔드포인트 (개인 폴더 및 공용 티어 권한 검증 포함)"""
    target_tier = (access_level or media_service.media_get_access_level(current_user, app_id)).upper()
    clean_sub_path = (sub_path or "").strip("/")

    if current_user.rank() < 4:
        if target_tier == "SYSTEM":
            raise HTTPException(status_code=403, detail="SYSTEM 영역 업로드는 관리자만 가능합니다.")
        if target_tier == "PRIVATE" and clean_sub_path and not _is_own_private_path(current_user, "PRIVATE", clean_sub_path):
            raise HTTPException(status_code=403, detail="본인의 개인 폴더에만 업로드할 수 있습니다.")

    assets = await media_service.media_process_upload(
        db=db,
        user=current_user,
        files=files,
        app_id=app_id,
        target_id=target_id,
        access_level=access_level,
        sub_path=sub_path
    )
    return assets

@router.post("/publish")
async def media_publish(
    req: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[v3.3] 내 파일함(PRIVATE)에 미리 업로드된 파일을 서비스 영역(PUBLIC/PROTECTED)으로 물리 복사(Publish)"""
    if not req.asset_ids:
        raise HTTPException(status_code=400, detail="선택된 파일이 없습니다.")
    target_tier = (req.access_level or "PUBLIC").upper()
    if current_user.rank() < 4 and target_tier not in ["PUBLIC", "PROTECTED"]:
        raise HTTPException(status_code=403, detail="서비스 배포는 PUBLIC 또는 PROTECTED 영역으로만 가능합니다.")

    published = media_service.media_publish_assets(
        db=db,
        user=current_user,
        asset_ids=req.asset_ids,
        app_id=req.app_id,
        target_id=req.target_id,
        access_level=target_tier,
        sub_path=req.sub_path
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
        message=f"개인 자산 {len(published)}건을 [{target_tier}] 영역으로 배포 복사했습니다."
    )
    return published

@router.get("/admin/list")
async def media_admin_list(
    tier: str = "PUBLIC",
    sub_path: str = "",
    recursive: bool = True,
    show_hidden: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    upper_tier = tier.upper()
    target_sub_path = sub_path.strip("/")
    is_admin = check_is_media_admin(current_user, db, action="read")

    # [v3.3 권한 정책: AppRegistry media 거버넌스 연동]
    # - 관리자(media 열람 권한 보유자): 전체 티어 및 전체 사용자 폴더 관제 가능
    # - 일반 사용자:
    #   1) PRIVATE 티어: 본인 폴더(USERS/{current_user.id})만 조회 가능 (미지정 시 자동 보정)
    #   2) SYSTEM 티어: 공용폴더(GLOBAL/OFFICE)는 Rank >= 2 열람 가능, 그 외 SYSTEM은 차단
    #   3) PROTECTED / PUBLIC 티어: Rank >= 2 탐색 가능
    if not is_admin:
        if upper_tier == "PRIVATE":
            if not target_sub_path:
                target_sub_path = f"USERS/{current_user.id}"
            elif not _is_own_private_path(current_user, "PRIVATE", target_sub_path):
                raise HTTPException(status_code=403, detail="본인의 개인 폴더만 조회할 수 있습니다.")
        elif upper_tier == "SYSTEM":
            if current_user.rank() < 2 or not (target_sub_path == "GLOBAL/OFFICE" or target_sub_path.startswith("GLOBAL/OFFICE/")):
                raise HTTPException(status_code=403, detail="Permission denied")
        elif upper_tier in ["PROTECTED", "PUBLIC"]:
            if current_user.rank() < 2:
                raise HTTPException(status_code=403, detail="Permission denied")
        else:
            raise HTTPException(status_code=403, detail="Permission denied")

    base_tier_folder = media_config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
    target_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, target_sub_path)
    _validate_safe_path(target_dir)
    
    if not os.path.exists(target_dir):
        media_service.safe_makedirs(target_dir)
        
    folders = []
    # 숨김/격리 파일 열람: 관리자이면서 show_hidden=True인 경우에만 허용
    allow_hidden = is_admin and show_hidden
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_dir():
                    # THUMB 폴더 및 tmp는 탐색기에서 항상 제외
                    if entry.name in [media_config.THUMB_FOLDER_NAME, 'tmp']:
                        continue
                    is_dot_or_del = entry.name.startswith('.') or entry.name.startswith('DEL_')
                    if not allow_hidden and is_dot_or_del:
                        continue
                    folders.append({
                        "name": entry.name,
                        "type": "folder",
                        "is_hidden": is_dot_or_del,
                        "path": os.path.join(target_sub_path, entry.name).strip("/")
                    })
    except Exception as e:
        print(f"Error scanning: {e}")

    normalized_sub_path = target_sub_path
    search_prefix = f"{base_tier_folder}/{normalized_sub_path}".strip("/")
    if normalized_sub_path:
        search_prefix += "/"
    
    base_filter = [
        MediaAsset.access_level == upper_tier,
    ]
    if not allow_hidden:
        base_filter.extend([
            MediaAsset.is_deleted == False,
            not_(MediaAsset.original_name.like(".%")),
            not_(MediaAsset.file_path.like("%/.%"))
        ])
    
    if recursive:
        base_filter.append(MediaAsset.file_path.like(f"{search_prefix}%"))
    else:
        base_filter.append(and_(
            MediaAsset.file_path.like(f"{search_prefix}%"),
            not_(MediaAsset.file_path.like(f"{search_prefix}%/%"))
        ))

    all_files = db.query(MediaAsset).filter(*base_filter).order_by(desc(MediaAsset.created_at)).all()

    return {
        "tier": tier,
        "current_path": target_sub_path,
        "show_hidden": allow_hidden,
        "folders": sorted(folders, key=lambda x: x['name']),
        "files": all_files 
    }

@router.post("/admin/folder/create")
async def media_admin_create_folder(
    req: FolderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    upper_tier = req.tier.upper()
    clean_sub_path = req.sub_path.strip("/")
    clean_folder_name = req.folder_name.strip("/")

    if not clean_folder_name or "/" in clean_folder_name or "\\" in clean_folder_name or clean_folder_name in [".", ".."]:
        raise HTTPException(status_code=400, detail="유효하지 않은 폴더 이름입니다.")

    # [v3.3 권한 정책] 일반 사용자는 본인 개인 폴더(PRIVATE/USERS/{id}) 하위에서만 폴더 생성 가능
    is_admin = check_is_media_admin(current_user, db, action="write")
    if not is_admin:
        if not clean_sub_path and upper_tier == "PRIVATE":
            clean_sub_path = f"USERS/{current_user.id}"
        if not _is_own_private_path(current_user, upper_tier, clean_sub_path):
            raise HTTPException(status_code=403, detail="본인의 개인 폴더에서만 새 폴더를 생성할 수 있습니다.")
    
    base_tier_folder = media_config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
    new_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, clean_sub_path, clean_folder_name)
    _validate_safe_path(new_dir)
    
    if os.path.exists(new_dir):
        raise HTTPException(status_code=400, detail="Folder already exists")
    
    media_service.safe_makedirs(new_dir)
    folder_full_path = os.path.join(clean_sub_path, clean_folder_name).strip("/")
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
        message=f"[{upper_tier}] /{folder_full_path} 폴더를 생성했습니다."
    )
    return {"message": "Folder created", "path": folder_full_path}

@router.post("/admin/backup")
async def media_admin_backup(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin_write)
):
    if req.folder_paths:
        raise HTTPException(status_code=400, detail="폴더 백업은 현재 지원되지 않습니다. 파일을 선택해 주세요.")

    from domain.system.task_service import enqueue_task
    task = enqueue_task(
        db=db,
        task_type="MEDIA_BACKUP",
        payload={"asset_ids": req.asset_ids, "target_user_id": current_user.id},
        priority=3
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
        message=f"미디어 자산 {len(req.asset_ids)}건 백업 태스크(ID: {task.id})를 예약했습니다."
    )
    return {"message": "백업 작업이 예약되었습니다.", "task_id": task.id}

@router.post("/admin/bulk-delete")
async def media_admin_bulk_delete(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    is_admin = check_is_media_admin(current_user, db, action="write")
    submitted_count = 0

    # 1. 파일별 비동기 삭제 예약 (일반 유저는 본인 소유 파일만 삭제 가능)
    if req.asset_ids:
        for asset_id in req.asset_ids:
            asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.is_deleted == False).first()
            if not asset:
                continue
            if not is_admin and asset.user_id != current_user.id:
                continue
            if media_service.delete_asset(db, asset_id):
                submitted_count += 1

    # 2. 폴더 내 모든 자산 식별 후 삭제 예약 (및 폴더 숨김 격리)
    if req.folder_paths:
        upper_tier = req.tier.upper()
        base_tier_folder = media_config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
        today_str = datetime.now().strftime("%Y%m%d")

        for fpath in req.folder_paths:
            clean_fpath = fpath.strip("/")
            # 일반 유저는 본인 개인 폴더(PRIVATE/USERS/{id}/...) 하위 폴더만 삭제 가능
            if not is_admin:
                if not _is_own_private_path(current_user, upper_tier, clean_fpath) or clean_fpath == f"USERS/{current_user.id}":
                    continue

            db_prefix = f"{base_tier_folder}/{clean_fpath}/"
            # 해당 폴더 하위의 모든 살아있는 자산 조회
            assets = db.query(MediaAsset).filter(
                MediaAsset.access_level == upper_tier,
                MediaAsset.file_path.like(f"{db_prefix}%"),
                MediaAsset.is_deleted == False
            ).all()
            
            for asset in assets:
                if media_service.delete_asset(db, asset.id):
                    submitted_count += 1

            # 물리 폴더 자체도 .DEL_{YYYYMMDD}_{폴더명} 으로 리네임하여 탐색기에서 숨김 격리
            abs_folder = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, clean_fpath)
            try:
                _validate_safe_path(abs_folder)
                if os.path.isdir(abs_folder):
                    parent_dir = os.path.dirname(abs_folder)
                    folder_base = os.path.basename(abs_folder)
                    if not folder_base.startswith("."):
                        isolated_folder = os.path.join(parent_dir, f"{media_config.PREFIX['DELETE']}{today_str}_{folder_base}")
                        os.rename(abs_folder, isolated_folder)
                        submitted_count += 1
            except Exception as e:
                print(f"Folder isolate error: {e}")

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
        message=f"총 {submitted_count}건의 미디어 자산/폴더를 삭제(격리) 처리했습니다."
    )

    return {"message": f"{submitted_count}건의 삭제 작업이 처리되었습니다."}

@router.post("/admin/gc")
async def media_admin_run_gc(
    req: GCRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_media_admin_write)
):
    from domain.system.task_service import enqueue_task
    task = enqueue_task(
        db=db,
        task_type="MEDIA_GC",
        payload={"indices": req.indices},
        scheduled_at=req.scheduled_at,
        unique_key=f"gc-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        priority=9
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
        message=f"미디어 시스템 가비지 컬렉션(GC) 작업을 예약했습니다. (Task ID: {task.id})"
    )
    return {"message": "시스템 정리(GC) 작업이 예약되었습니다.", "task_id": task.id}

@router.post("/delete/{asset_id}")
async def media_admin_delete(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.is_deleted == False).first()
    if not asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 이미 삭제되었습니다.")

    is_admin = check_is_media_admin(current_user, db, action="write")
    # [v3.3 권한 정책] 본인 소유 자산이거나 관리자인 경우 삭제(격리) 허용
    if asset.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="본인의 파일만 삭제할 수 있습니다.")
    
    asset_name = asset.original_name
    success = media_service.delete_asset(db, asset_id)
    if not success:
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
        message=f"미디어 자산 [{asset_id}] {asset_name}을(를) 삭제(격리) 처리했습니다."
    )
    return {"message": "Successfully deleted"}
