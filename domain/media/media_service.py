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
            
        # 3. 경로 확정 (사용자 지정 경로는 입력 대소문자 그대로 보존, 시스템 기본 경로는 대문자)
        if sub_path:
            safe_sub_path = sub_path.strip("/")
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
        from datetime import datetime, timedelta
        expires_at = (datetime.now() + timedelta(days=60)).isoformat()
        meta_info = {
            "original_name": original_name,
            "has_original": True,
            "original_expires_at": expires_at,
            "original_purged": False
        }
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


def media_publish_assets(
    db: Session,
    user: User,
    asset_ids: List[int],
    app_id: str = "general",
    target_id: Optional[str] = None,
    access_level: str = "PUBLIC",
    sub_path: Optional[str] = None
) -> List[MediaAsset]:
    """
    [v3.3] 개인 보관함(PRIVATE 등)에 미리 업로드된 파일을 서비스 영역(PUBLIC/PROTECTED)으로
    직접 업로드(media_process_upload)와 동일한 경로·네이밍·썸네일 규칙으로 물리 복사(Publish)합니다.
    """
    import shutil

    results = []
    final_access_level = access_level.upper() if access_level else media_get_access_level(user, app_id)

    source_assets = db.query(MediaAsset).filter(
        MediaAsset.id.in_(asset_ids),
        MediaAsset.is_deleted == False
    ).all()

    for src_asset in source_assets:
        # 권한 확인: 본인 소유 파일이거나 관리자(rank >= 4)만 배포 가능
        if src_asset.user_id != user.id and user.rank() < 4:
            continue

        src_abs_path = os.path.join(config.MEDIA_ROOT, src_asset.file_path)
        if not os.path.exists(src_abs_path):
            logger.warning(f"[Media Publish] 원본 파일 없음: {src_abs_path}")
            continue

        original_name = src_asset.original_name
        file_ext = os.path.splitext(original_name)[1].upper()
        if not file_ext:
            file_ext = os.path.splitext(src_asset.file_path)[1].upper()
        mime_type = src_asset.mime_type or "application/octet-stream"
        category = src_asset.category or (
            config.MEDIA_CATEGORIES["IMAGE"] if mime_type.startswith("image/") else config.MEDIA_CATEGORIES["DOCUMENT"]
        )

        # 경로 확정 (직접 업로드와 100% 동일 규칙)
        if sub_path:
            safe_sub_path = sub_path.strip("/")
            tier_folder = config.MEDIA_TIERS.get(final_access_level, "PUBLIC")
            relative_dir = os.path.join(tier_folder, safe_sub_path).replace("\\", "/")
        else:
            relative_dir = media_generate_path(final_access_level, category, user.id)

        abs_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
        safe_makedirs(abs_dir)

        # 새 UUID 부여 및 네이밍 규칙 적용 (원본 삭제와 완전 분리)
        unique_uuid = str(uuid.uuid4())
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            filename = f"{config.PREFIX['IMAGE']}{unique_uuid}{file_ext}"
        else:
            filename = f"{config.PREFIX['DOC']}{unique_uuid[:8]}_{original_name}{file_ext}"

        filename = get_unique_filename(abs_dir, filename)
        relative_file_path = os.path.join(relative_dir, filename).replace("\\", "/")
        abs_file_path = os.path.join(abs_dir, filename)

        need_bg_thumb_gen = False
        thumb_main_path = None

        # [v3.5 대원칙]:
        # 1. 이미지(IMAGE): 원본 복사 생략! 썸네일 3종(SM, MD, LG)만 물리 복사하여 스토리지 90% 절감
        # 2. 문서(DOC): 원본 물리 복사
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            meta_info = {
                "original_name": original_name,
                "published_from": src_asset.id,
                "has_original": False,  # 복제본은 원본 미포함 (상세보기에서 원본 다운로드 비활성화)
                "thumbs": {}
            }
            file_size = src_asset.file_size or 0
            thumb_dir = os.path.join(abs_dir, config.THUMB_FOLDER_NAME)
            safe_makedirs(thumb_dir)

            # 1. 원본 자산(src_asset)에 이미 존재하는 썸네일 3종(SM, MD, LG) 물리 복사
            src_dir = os.path.dirname(src_abs_path)
            src_base = os.path.basename(src_asset.file_path)
            src_uuid = src_base.replace(config.PREFIX['IMAGE'], "").split('.')[0]

            copied_thumbs = {}
            for size_key in ["SM", "MD", "LG"]:
                cfg = config.MEDIA_THUMB_CONFIG[size_key]
                src_thumb_file = f"{config.PREFIX['THUMB']}{src_uuid}_{cfg['suffix']}.WEBP"
                src_thumb_path = os.path.join(src_dir, config.THUMB_FOLDER_NAME, src_thumb_file)

                # 레거시 경로 대응
                if not os.path.exists(src_thumb_path):
                    legacy_path = os.path.join(src_dir, "thumbnails", f"{src_uuid}_{size_key.lower()}.webp")
                    if os.path.exists(legacy_path):
                        src_thumb_path = legacy_path

                if os.path.exists(src_thumb_path):
                    dst_thumb_file = f"{config.PREFIX['THUMB']}{unique_uuid}_{cfg['suffix']}.WEBP"
                    dst_thumb_path = os.path.join(thumb_dir, dst_thumb_file)
                    shutil.copy2(src_thumb_path, dst_thumb_path)
                    os.chmod(dst_thumb_path, 0o644)

                    rel_thumb_path = os.path.join(relative_dir, config.THUMB_FOLDER_NAME, dst_thumb_file).replace("\\", "/")
                    copied_thumbs[size_key.lower()] = rel_thumb_path
                    if size_key == "SM":
                        thumb_main_path = rel_thumb_path

            # 원본 자산에 썸네일이 없었던 경우: 원본(src_abs_path)에서 썸네일을 생성하여 저장 (원본 복사는 하지 않음)
            if not copied_thumbs and os.path.exists(src_abs_path):
                try:
                    with Image.open(src_abs_path) as img:
                        meta_info["width"], meta_info["height"] = img.size
                        if img.mode in ("P", "CMYK"):
                            img = img.convert("RGB")
                        for size_key in ["SM", "MD", "LG"]:
                            cfg = config.MEDIA_THUMB_CONFIG[size_key]
                            t_img = img.copy()
                            t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)
                            t_filename = f"{config.PREFIX['THUMB']}{unique_uuid}_{cfg['suffix']}.WEBP"
                            t_abs = os.path.join(thumb_dir, t_filename)
                            t_rel = os.path.join(relative_dir, config.THUMB_FOLDER_NAME, t_filename).replace("\\", "/")
                            t_img.save(t_abs, "WEBP", quality=config.WEBP_QUALITY)
                            os.chmod(t_abs, 0o644)
                            copied_thumbs[size_key.lower()] = t_rel
                            if size_key == "SM":
                                thumb_main_path = t_rel
                except Exception as e:
                    logger.error(f"[Media Publish Error] Thumbnail gen from src failed: {e}")

            meta_info["thumbs"] = copied_thumbs
        else:
            # 일반 문서인 경우: 원본 물리 복사
            shutil.copy2(src_abs_path, abs_file_path)
            os.chmod(abs_file_path, 0o644)
            file_size = os.path.getsize(abs_file_path)
            meta_info = {"original_name": original_name, "published_from": src_asset.id, "has_original": True}

        new_asset = MediaAsset(
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
        db.add(new_asset)
        db.flush()

        # 썸네일이 누락된 경우에만 비동기 큐 예약 (완전 복사 시 워커 불필요)
        if need_bg_thumb_gen:
            enqueue_task(
                db=db,
                task_type="THUMB_GEN",
                payload={"asset_id": new_asset.id},
                unique_key=f"thumb-gen-{new_asset.id}",
                priority=7
            )

        results.append(new_asset)

    db.commit()
    return results
