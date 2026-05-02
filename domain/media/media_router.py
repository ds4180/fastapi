from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, not_
from typing import List, Optional
from database import get_db
from domain.user.user_router import get_current_user
from domain.media import media_service, media_config
from models import User, MediaAsset
import os
import shutil
import io
import zipfile
from datetime import datetime
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(
    prefix="/media",
    tags=["Media System"]
)

class FolderCreateRequest(BaseModel):
    tier: str
    sub_path: str
    folder_name: str

class BulkActionRequest(BaseModel):
    asset_ids: List[int] = []
    folder_paths: List[str] = [] 
    tier: str = "PUBLIC"

class GCRequest(BaseModel):
    indices: List[int] = [1, 2, 3, 4, 5]
    scheduled_at: Optional[datetime] = None

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
    if size in ["SM", "MD", "LG"]:
        thumb_name = f"TMB_{asset.id}_{size}.WEBP"
        thumb_path = os.path.join(media_config.MEDIA_ROOT, media_config.THUMB_FOLDER_NAME, thumb_name)
        
        if os.path.exists(thumb_path):
            target_rel_path = f"{media_config.THUMB_FOLDER_NAME}/{thumb_name}"
        else:
            # [v3.2 Self-healing] 썸네일이 없으면 즉시 재생성 태스크 예약
            from domain.system.task_service import enqueue_task
            enqueue_task(db, "THUMB_GEN", {"asset_id": asset.id}, priority=2)
            db.commit()

    internal_prefix = TIER_INTERNAL_MAP.get(asset.access_level, "/PUBLIC/")
    if size and target_rel_path.startswith(media_config.THUMB_FOLDER_NAME):
        internal_prefix = "/THUMB/"
        redirect_path = f"{internal_prefix}{os.path.basename(target_rel_path)}"
    else:
        # 실제 파일 경로에서 티어명 제외하고 전달
        path_without_tier = "/".join(target_rel_path.split("/")[1:])
        redirect_path = f"{internal_prefix}{path_without_tier}"

    return Response(
        headers={
            "X-Accel-Redirect": redirect_path,
            "Content-Type": asset.mime_type or "application/octet-stream"
        }
    )

@router.get("/admin/stats")
async def media_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    total_count = db.query(func.count(MediaAsset.id)).filter(MediaAsset.is_deleted == False).scalar()
    total_size = db.query(func.sum(MediaAsset.file_size)).filter(MediaAsset.is_deleted == False).scalar() or 0
    
    tier_stats = db.query(
        MediaAsset.access_level,
        func.count(MediaAsset.id),
        func.sum(MediaAsset.file_size)
    ).filter(MediaAsset.is_deleted == False).group_by(MediaAsset.access_level).all()
    
    tier_summary = { row[0]: {"count": row[1], "size": row[2] or 0} for row in tier_stats }
    
    folder_summary = {}
    for tier_key, tier_folder in media_config.MEDIA_TIERS.items():
        tier_path = os.path.join(media_config.MEDIA_ROOT, tier_folder)
        size = 0
        count = 0
        if os.path.exists(tier_path):
            for dirpath, dirnames, filenames in os.walk(tier_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    size += os.path.getsize(fp)
                    count += 1
        folder_summary[tier_key] = {"size": size, "count": count}

    return {
        "total_count": total_count,
        "total_size_bytes": total_size,
        "tier_summary": tier_summary,
        "folder_physical_summary": folder_summary
    }

@router.get("/admin/recent")
async def media_admin_recent(
    limit: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
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
    """[v3.2] 통합 파일 업로드 엔드포인트"""
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

@router.get("/admin/list")
async def media_admin_list(
    tier: str = "PUBLIC",
    sub_path: str = "",
    recursive: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    base_tier_folder = media_config.MEDIA_TIERS.get(tier.upper(), "PUBLIC")
    target_sub_path = sub_path.strip("/").upper()
    target_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, target_sub_path)
    
    if not os.path.exists(target_dir):
        media_service.safe_makedirs(target_dir)
        
    folders = []
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith('.'):
                    if entry.name not in [media_config.THUMB_FOLDER_NAME, 'tmp'] and not entry.name.startswith('DEL_'):
                        folders.append({
                            "name": entry.name,
                            "type": "folder",
                            "path": os.path.join(sub_path, entry.name).strip("/")
                        })
    except Exception as e:
        print(f"Error scanning: {e}")

    normalized_sub_path = sub_path.strip("/").upper()
    search_prefix = f"{base_tier_folder}/{normalized_sub_path}".strip("/")
    if normalized_sub_path:
        search_prefix += "/"
    
    base_filter = [
        MediaAsset.access_level == tier.upper(),
        MediaAsset.is_deleted == False
    ]
    
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
        "current_path": sub_path,
        "folders": sorted(folders, key=lambda x: x['name']),
        "files": all_files 
    }

@router.post("/admin/folder/create")
async def media_admin_create_folder(
    req: FolderCreateRequest,
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "PUBLIC")
    new_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, req.sub_path.upper(), req.folder_name.upper())
    
    if os.path.exists(new_dir):
        raise HTTPException(status_code=400, detail="Folder already exists")
    
    media_service.safe_makedirs(new_dir)
    return {"message": "Folder created", "path": os.path.join(req.sub_path, req.folder_name).upper()}

@router.post("/admin/backup")
async def media_admin_backup(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
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
    return {"message": "백업 작업이 예약되었습니다.", "task_id": task.id}

@router.post("/admin/bulk-delete")
async def media_admin_bulk_delete(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    deleted_count = 0
    today = datetime.now().strftime("%Y%m%d")
    del_root = os.path.join(media_config.MEDIA_ROOT, f"DEL_{today}")
    os.makedirs(del_root, exist_ok=True)

    # 파일 삭제
    if req.asset_ids:
        assets = db.query(MediaAsset).filter(MediaAsset.id.in_(req.asset_ids)).all()
        for asset in assets:
            src = os.path.join(media_config.MEDIA_ROOT, asset.file_path)
            if os.path.exists(src):
                dst = os.path.join(del_root, asset.file_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
            asset.is_deleted = True
            asset.deleted_at = datetime.now()
            deleted_count += 1

    # 폴더 삭제
    if req.folder_paths:
        base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "PUBLIC")
        for fpath in req.folder_paths:
            src_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, fpath.upper())
            if os.path.exists(src_dir):
                dst_dir = os.path.join(del_root, base_tier_folder, fpath.upper())
                os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
                shutil.move(src_dir, dst_dir)
                
                # DB 하위 파일들도 삭제 처리
                db_prefix = f"{base_tier_folder}/{fpath.upper()}/"
                db.query(MediaAsset).filter(
                    MediaAsset.access_level == req.tier.upper(),
                    MediaAsset.file_path.like(f"{db_prefix}%")
                ).update({"is_deleted": True, "deleted_at": datetime.now()}, synchronize_session=False)

    db.commit()
    return {"message": f"{deleted_count} items deleted"}

@router.post("/admin/gc")
async def media_admin_run_gc(
    req: GCRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
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
    return {"message": "시스템 정리(GC) 작업이 예약되었습니다.", "task_id": task.id}

@router.post("/delete/{asset_id}")
async def media_admin_delete(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    success = media_service.delete_asset(db, asset_id)
    if not success: raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 삭제에 실패했습니다.")
    return {"message": "Successfully deleted"}
