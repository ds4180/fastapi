from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from domain.user.user_router import get_current_user
from domain.media import media_service
from models import User, MediaAsset
from sqlalchemy import desc
import os
import shutil
from datetime import datetime
from domain.media import media_config
from fastapi.responses import StreamingResponse
from fastapi import Response
import io
import zipfile
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

# [v3.2] 보안 미디어 서빙 (X-Accel-Redirect)
TIER_INTERNAL_MAP = {
    "PROTECTED": "/protected_files/",
    "PRIVATE": "/private_files/",
    "SYSTEM": "/system_files/",
}

@router.get("/serve/{asset_id}")
async def media_secure_serve(
    asset_id: int,
    size: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """보안 Tier 미디어 서빙 - 권한 검증 후 Nginx X-Accel-Redirect로 전달"""
    asset = db.query(MediaAsset).filter(
        MediaAsset.id == asset_id, MediaAsset.is_deleted == False
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다.")

    tier = asset.access_level.upper()

    # 권한 검증
    if tier == "PROTECTED":
        pass  # 로그인 사용자 전체 허용 (get_current_user 통과 시 OK)
    elif tier == "PRIVATE":
        if asset.user_id != current_user.id and current_user.rank() < 4:
            raise HTTPException(status_code=403, detail="본인 소유 파일만 접근 가능합니다.")
    elif tier == "SYSTEM":
        if current_user.rank() < 4:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    else:
        raise HTTPException(status_code=400, detail="PUBLIC 자산은 직접 URL로 접근하세요.")

    # 서빙할 파일 경로 결정 (썸네일 or 원본)
    serve_path = asset.file_path
    if size:
        target_size = size.lower()
        if asset.meta_info and asset.meta_info.get("thumbs", {}).get(target_size):
            serve_path = asset.meta_info["thumbs"][target_size]
        elif asset.thumbnail_path:
            serve_path = asset.thumbnail_path

    # Tier별 internal 경로 매핑
    internal_prefix = TIER_INTERNAL_MAP.get(tier)
    # file_path: "PROTECTED/IMAGE/2026/05/02/IMG_xxx.JPG" → Tier 접두어 제거
    relative = serve_path.split("/", 1)[1] if "/" in serve_path else serve_path

    return Response(
        headers={
            "X-Accel-Redirect": f"{internal_prefix}{relative}",
            "Content-Type": asset.mime_type or "application/octet-stream",
        }
    )

@router.post("/upload")
async def media_upload(
    files: List[UploadFile] = File(...),
    app_id: str = "general",
    target_id: str = None,
    access_level: str = None,
    sub_path: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def media_list(
    app_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(MediaAsset).filter(MediaAsset.user_id == current_user.id, MediaAsset.is_deleted == False)
    if app_id:
        query = query.filter(MediaAsset.app_id == app_id)
    return query.order_by(MediaAsset.created_at.desc()).all()

@router.get("/admin/stats")
async def media_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    from sqlalchemy import func
    total_count = db.query(MediaAsset).filter(MediaAsset.is_deleted == False).count()
    total_size = db.query(func.sum(MediaAsset.file_size)).filter(MediaAsset.is_deleted == False).scalar() or 0
    
    tier_stats = db.query(
        MediaAsset.access_level,
        func.count(MediaAsset.id),
        func.sum(MediaAsset.file_size)
    ).filter(MediaAsset.is_deleted == False).group_by(MediaAsset.access_level).all()
    
    tier_summary = { row[0]: {"count": row[1], "size": row[2] or 0} for row in tier_stats }
    
    folder_summary = {}
    for tier in ['public', 'protected', 'private', 'system', 'tmp']:
        tier_path = os.path.join(media_config.MEDIA_ROOT, tier)
        size = 0
        count = 0
        if os.path.exists(tier_path):
            for dirpath, dirnames, filenames in os.walk(tier_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    size += os.path.getsize(fp)
                    count += 1
        folder_summary[tier] = {"size": size, "count": count}

    return {
        "total_count": total_count,
        "total_size_bytes": total_size,
        "tier_summary": tier_summary,
        "folder_physical_summary": folder_summary
    }

@router.get("/admin/list")
async def media_admin_list(
    tier: str = "PUBLIC",
    sub_path: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    # [v3.1] 대문자 티어 폴더 사용
    base_tier_folder = media_config.MEDIA_TIERS.get(tier.upper(), "PUBLIC")
    target_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, sub_path.strip("/"))
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        os.chmod(target_dir, 0o775)
        
    folders = []
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith('.'):
                    # [v3.1] THUMB 폴더 및 삭제 접두어 제외
                    if entry.name not in [media_config.THUMB_FOLDER_NAME, 'tmp'] and not entry.name.startswith('DEL_'):
                        folders.append({
                            "name": entry.name,
                            "type": "folder",
                            "path": os.path.join(sub_path, entry.name).strip("/")
                        })
    except Exception as e:
        print(f"Error scanning: {e}")

    # [v3.1] DB 조회 시 대문자 경로 검색
    search_prefix = f"{base_tier_folder}/{sub_path.strip('/')}".strip("/")
    if sub_path:
        search_prefix += "/"
    
    all_recursive_files = db.query(MediaAsset).filter(
        MediaAsset.access_level == tier.upper(),
        MediaAsset.file_path.like(f"{search_prefix}%"),
        MediaAsset.is_deleted == False
    ).order_by(desc(MediaAsset.created_at)).all()

    return {
        "tier": tier,
        "current_path": sub_path,
        "folders": sorted(folders, key=lambda x: x['name']),
        "files": all_recursive_files 
    }

@router.post("/admin/folder/create")
async def media_admin_create_folder(
    req: FolderCreateRequest,
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "public")
    target_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, req.sub_path.strip("/"), req.folder_name.strip("/"))
    
    try:
        os.makedirs(target_dir, exist_ok=True)
        os.chmod(target_dir, 0o775) # 👈 권한 강제 설정
        return {"message": "Folder created", "path": target_dir}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 생성 실패: {str(e)}")

@router.post("/admin/backup")
async def media_admin_backup(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    # [v3.2] 대문자 Tier 표준 적용 및 개인 폴더 경로 매칭
    backup_sub_path = f"USERS/{current_user.id}/ADMIN_BACKUPS/{today_str}"
    backup_root = os.path.join(
        media_config.MEDIA_ROOT, "PRIVATE", backup_sub_path
    )
    
    success_count = 0
    errors = []
    
    if req.asset_ids:
        assets = db.query(MediaAsset).filter(MediaAsset.id.in_(req.asset_ids)).all()
        for asset in assets:
            try:
                src_path = os.path.join(media_config.MEDIA_ROOT, asset.file_path)
                if not os.path.exists(src_path): continue
                category_dir = "IMAGE" if asset.category == "image" else "DOCUMENT"
                target_dir = os.path.join(backup_root, category_dir)
                os.makedirs(target_dir, exist_ok=True)
                os.chmod(target_dir, 0o775)
                
                dst_path = os.path.join(target_dir, asset.original_name)
                counter = 1
                name, ext = os.path.splitext(asset.original_name)
                while os.path.exists(dst_path):
                    dst_path = os.path.join(target_dir, f"{name}({counter}){ext}")
                    counter += 1
                shutil.copy2(src_path, dst_path)
                
                # [v3.2] 파일 탐색기에 표시되도록 DB 기록
                new_asset = MediaAsset(
                    user_id=current_user.id,
                    access_level="PRIVATE",
                    app_id="admin_backup",
                    target_id=today_str,
                    original_name=os.path.basename(dst_path),
                    file_path=os.path.join("PRIVATE", backup_sub_path, category_dir, os.path.basename(dst_path)),
                    file_size=asset.file_size,
                    mime_type=asset.mime_type,
                    category=asset.category,
                    meta_info={} 
                )
                db.add(new_asset)
                success_count += 1
            except Exception as e: errors.append(f"File backup fail: {str(e)}")
        db.commit()

    if req.folder_paths:
        base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "PUBLIC")
        for sub in req.folder_paths:
            try:
                src_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, sub.strip("/"))
                if os.path.isdir(src_dir):
                    dst_dir = os.path.join(backup_root, "FOLDERS", os.path.basename(src_dir))
                    os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
                    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                    
                    # [v3.2] 폴더 복사 시 내부 파일들을 DB에 재등록
                    for root, _, files in os.walk(dst_dir):
                        for f in files:
                            full_path = os.path.join(root, f)
                            rel_path = os.path.relpath(full_path, media_config.MEDIA_ROOT)
                            new_asset = MediaAsset(
                                user_id=current_user.id,
                                access_level="PRIVATE",
                                app_id="admin_backup",
                                target_id=today_str,
                                original_name=f,
                                file_path=rel_path,
                                file_size=os.path.getsize(full_path),
                                mime_type="application/octet-stream",
                                category="document", # 기본값
                                meta_info={}
                            )
                            db.add(new_asset)
                    success_count += 1
            except Exception as e: errors.append(f"Folder backup fail: {str(e)}")
        db.commit()
            
    return {"message": "Backup finished", "success_count": success_count, "backup_location": backup_root, "errors": errors}

@router.post("/admin/bulk-delete")
async def media_admin_bulk_delete(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    deleted_count = 0
    errors = []
    
    for aid in req.asset_ids:
        try:
            if media_service.delete_asset(db, aid): deleted_count += 1
        except Exception as e: errors.append(f"File delete fail (ID {aid}): {str(e)}")
            
    if req.folder_paths:
        base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "public")
        for sub in req.folder_paths:
            try:
                target = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, sub.strip("/"))
                if os.path.isdir(target):
                    parent = os.path.dirname(target)
                    bname = os.path.basename(target)
                    new_name = os.path.join(parent, f"DEL_{datetime.now().strftime('%Y%m%d')}_{bname}")
                    os.rename(target, new_name)
                    deleted_count += 1
            except Exception as e: errors.append(f"Folder isolate fail ({sub}): {str(e)}")

    return {"message": "Bulk action finished", "count": deleted_count, "errors": errors}

@router.post("/admin/zip-download")
async def media_admin_zip_download(
    req: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    zip_buffer = io.BytesIO()
    has_files = False
    
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if req.asset_ids:
                assets = db.query(MediaAsset).filter(MediaAsset.id.in_(req.asset_ids)).all()
                for asset in assets:
                    abs_path = os.path.join(media_config.MEDIA_ROOT, asset.file_path)
                    if os.path.exists(abs_path) and os.path.isfile(abs_path):
                        zip_file.write(abs_path, asset.original_name)
                        has_files = True
            
            if req.folder_paths:
                base_tier_folder = media_config.MEDIA_TIERS.get(req.tier.upper(), "public")
                for sub in req.folder_paths:
                    src_dir = os.path.join(media_config.MEDIA_ROOT, base_tier_folder, sub.strip("/"))
                    if os.path.isdir(src_dir):
                        parent_dir = os.path.dirname(src_dir)
                        for root, dirs, files in os.walk(src_dir):
                            for file in files:
                                abs_fpath = os.path.join(root, file)
                                rel_fpath = os.path.relpath(abs_fpath, parent_dir)
                                zip_file.write(abs_fpath, rel_fpath)
                                has_files = True

        if not has_files: raise HTTPException(status_code=400, detail="압축할 파일이 없습니다.")
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/x-zip-compressed",
            headers={"Content-Disposition": f"attachment; filename=admin_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"}
        )
    except Exception as e: raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

@router.get("/admin/recent")
async def media_admin_recent(
    limit: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.rank() < 4:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    
    result = {}
    tiers = ["PUBLIC", "PROTECTED", "PRIVATE", "SYSTEM"]
    for tier in tiers:
        items = db.query(MediaAsset).filter(MediaAsset.access_level == tier, MediaAsset.is_deleted == False).order_by(desc(MediaAsset.created_at)).limit(limit).all()
        result[tier.lower()] = items
    return result

@router.delete("/delete/{asset_id}")
async def media_delete(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    success = media_service.delete_asset(db, asset_id)
    if not success: raise HTTPException(status_code=404, detail="자산을 찾을 수 없거나 삭제에 실패했습니다.")
    return {"message": "Successfully deleted"}
