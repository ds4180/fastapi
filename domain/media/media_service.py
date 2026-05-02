import os
import uuid
import aiofiles
import logging
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import UploadFile
from PIL import Image
from sqlalchemy.orm import Session
from models import MediaAsset, User, SystemTask
from domain.media import media_config as config
from domain.system.task_service import enqueue_task

logger = logging.getLogger("media_service")

# ==============================================================================
# [Media System Domain Service v3.2]
# ==============================================================================

def safe_makedirs(path, mode=0o775):
    """[v3.2 Root Cause Fix] 모든 계층의 폴더 권한을 확실히 보장하며 폴더 생성"""
    if not os.path.exists(path):
        os.makedirs(path, mode=mode, exist_ok=True)
        # 상위로 올라가며 UPLOAD_DIR(MEDIA_ROOT)를 만날 때까지 권한 수정
        curr = path
        root_path = os.path.abspath(config.MEDIA_ROOT)
        while curr:
            abs_curr = os.path.abspath(curr)
            if len(abs_curr) <= len(root_path): break
            try:
                os.chmod(abs_curr, mode)
            except: break
            curr = os.path.dirname(curr)

def media_get_access_level(user: User, app_id: str) -> str:
    if user.rank() >= 4:
        return "PUBLIC"
    if app_id in ["identity", "secure_doc"]:
        return "PRIVATE"
    return "PUBLIC"

def media_generate_path(access_level: str, category: str, user_id: int) -> str:
    now = datetime.now()
    date_path = now.strftime("%Y/%m/%d")
    tier_folder = config.MEDIA_TIERS.get(access_level.upper(), "PUBLIC")
    category_folder = category.upper() 

    if access_level.upper() == "PRIVATE":
        return os.path.join(tier_folder, "USERS", str(user_id), category_folder, date_path)
    return os.path.join(tier_folder, category_folder, date_path)

def get_unique_filename(directory: str, filename: str) -> str:
    name, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{name}_{counter}{ext}"
        counter += 1
    return new_filename

async def media_process_upload(
    db: Session,
    user: User,
    files: List[UploadFile],
    app_id: str = "general",
    target_id: str = None,
    access_level: Optional[str] = None,
    sub_path: Optional[str] = None
) -> List[MediaAsset]:
    results = []
    final_access_level = access_level.upper() if access_level else media_get_access_level(user, app_id)

    for file in files:
        # 1. 파일 정보 및 확장자 대문자화
        original_name = file.filename
        file_ext = os.path.splitext(original_name)[1].upper()
        mime_type = file.content_type or "application/octet-stream"
        
        # 2. 카테고리 판별
        category = config.MEDIA_CATEGORIES["IMAGE"] if mime_type.startswith("image/") else config.MEDIA_CATEGORIES["DOCUMENT"]
            
        # 3. 경로 확정 (시스템-대문자, 유저-소문자)
        if sub_path:
            # [v3.1] 시스템 표준에 따라 하위 경로도 대문자로 치환 (GLOBAL/OFFICE 등)
            safe_sub_path = sub_path.strip("/").upper() 
            tier_folder = config.MEDIA_TIERS.get(final_access_level.upper(), "PUBLIC")
            relative_dir = os.path.join(tier_folder, safe_sub_path).replace("\\", "/")
        else:
            # 기본 표준 경로 생성
            relative_dir = media_generate_path(final_access_level, category, user.id)
            
        abs_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
        safe_makedirs(abs_dir) 
        
        # 4. 네이밍 규칙 적용
        unique_uuid = str(uuid.uuid4())
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            filename = f"{config.PREFIX['IMAGE']}{unique_uuid}{file_ext}"
        else:
            filename = f"{config.PREFIX['DOC']}{unique_uuid[:8]}_{original_name}{file_ext}"

        filename = get_unique_filename(abs_dir, filename)
        relative_file_path = os.path.join(relative_dir, filename).replace("\\", "/")
        abs_file_path = os.path.join(abs_dir, filename)

        # 5. 원본 파일 물리적 저장
        content = await file.read()
        async with aiofiles.open(abs_file_path, "wb") as f:
            await f.write(content)
        os.chmod(abs_file_path, 0o644) # [v3.2] 원본 파일 읽기 권한 보장
        
        file_size = len(content)
        meta_info = {"original_name": original_name}
        thumb_main_path = None

        # 6. 이미지 썸네일 (SM 동기 생성)
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            try:
                with Image.open(abs_file_path) as img:
                    meta_info["width"], meta_info["height"] = img.size
                    thumb_dir = os.path.join(abs_dir, config.THUMB_FOLDER_NAME)
                    safe_makedirs(thumb_dir)
                    
                    if img.mode in ("P", "CMYK"):
                        img = img.convert("RGB")
                    
                    # [SM] 즉시 생성
                    sm_cfg = config.MEDIA_THUMB_CONFIG["SM"]
                    sm_img = img.copy()
                    sm_img.thumbnail(sm_cfg["size"], Image.Resampling.LANCZOS)
                    sm_filename = f"{config.PREFIX['THUMB']}{unique_uuid}_{sm_cfg['suffix']}.WEBP"
                    sm_abs_path = os.path.join(thumb_dir, sm_filename)
                    sm_rel_path = os.path.join(relative_dir, config.THUMB_FOLDER_NAME, sm_filename).replace("\\", "/")
                    
                    # ⚠️ 오타 수정: WEBP_QUALITY 사용
                    sm_img.save(sm_abs_path, "WEBP", quality=config.WEBP_QUALITY)
                    os.chmod(sm_abs_path, 0o644) # [v3.2] SM 썸네일 읽기 권한 보장
                    
                    meta_info["thumbs"] = {"sm": sm_rel_path}
                    thumb_main_path = sm_rel_path
            except Exception as e:
                logger.error(f"[Media Error] SM Thumbnail failed: {e}")

        # 7. DB 레코드 생성 및 Flush (ID 확보)
        asset = MediaAsset(
            user_id=user.id,
            access_level=final_access_level,
            app_id=app_id,
            target_id=target_id,
            original_name=original_name,
            file_path=relative_file_path,
            thumbnail_path=thumb_main_path,
            meta_info=meta_info,
            file_size=file_size,
            mime_type=mime_type,
            category=category
        )
        db.add(asset)
        db.flush() 

        # 8. 고해상도 썸네일 비동기 예약 (확보된 asset.id 사용)
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            enqueue_task(
                db=db,
                task_type="THUMB_GEN",
                payload={"asset_id": asset.id},
                unique_key=f"thumb-gen-{asset.id}",
                priority=7
            )
        
        results.append(asset)

    db.commit() # 모든 파일 처리 후 최종 커밋
    return results

def delete_asset(db: Session, asset_id: int):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset: return False
    
    asset.is_deleted = True
    asset.deleted_at = datetime.now()
    
    enqueue_task(
        db=db,
        task_type="MEDIA_ISOLATE",
        payload={"asset_id": asset.id, "file_path": os.path.join(config.MEDIA_ROOT, asset.file_path)},
        unique_key=f"isolate-{asset.id}"
    )
    db.commit()
    return True
