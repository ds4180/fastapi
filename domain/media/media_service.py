import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import aiofiles
from fastapi import UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from domain.media import media_config as config
from domain.media.media_policy_service import (
    check_is_media_admin,
    get_media_settings,
    get_thumb_specs_from_settings,
    validate_upload_file_constraints,
)
from domain.system.task_service import enqueue_task
from models import MediaAsset, User

logger = logging.getLogger("media_service")


def safe_makedirs(path: str, mode: int = 0o775) -> None:
    """모든 계층의 폴더 권한을 보장하며 디렉터리를 생성합니다."""
    if not os.path.exists(path):
        os.makedirs(path, mode=mode, exist_ok=True)
        curr = path
        root_path = os.path.abspath(config.MEDIA_ROOT)
        while curr:
            abs_curr = os.path.abspath(curr)
            if len(abs_curr) <= len(root_path):
                break
            try:
                os.chmod(abs_curr, mode)
            except Exception:
                break
            curr = os.path.dirname(curr)


def media_get_access_level(user: User, app_id: str, db: Optional[Session] = None) -> str:
    """명시적 access_level 미전달 시 동적 설정(default_upload_tier_for_user)을 반환합니다."""
    if db is not None:
        settings = get_media_settings(db)
        if check_is_media_admin(user, db, action="write"):
            return "PUBLIC"
        return str(settings.get("default_upload_tier_for_user", "PUBLIC")).upper()
    return "PUBLIC"


def classify_media_category(mime_type: str, file_ext_lower: str) -> str:
    if (mime_type or "").startswith("image/"):
        return config.MEDIA_CATEGORIES["IMAGE"]
    if file_ext_lower in config.ARCHIVE_EXTENSIONS:
        return config.MEDIA_CATEGORIES["ARCHIVE"]
    return config.MEDIA_CATEGORIES["DOCUMENT"]


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
    target_id: Optional[str] = None,
    access_level: Optional[str] = None,
    sub_path: Optional[str] = None,
) -> List[MediaAsset]:
    """동적 정책(용량·확장자·WebP 품질·해상도·원본 보관일수)을 적용하여 파일을 업로드합니다."""
    settings = get_media_settings(db)
    thumb_specs = get_thumb_specs_from_settings(settings)
    webp_quality = int(settings.get("webp_quality", config.WEBP_QUALITY))
    auto_expiry = bool(settings.get("enable_original_auto_expiry", True))
    keep_days = int(settings.get("original_keep_days", 60))

    final_access_level = (
        access_level.upper() if access_level else media_get_access_level(user, app_id, db=db)
    )

    # 1차: 스트림 읽기 및 정책 제약 조건 선행 검증 (부분 저장 방지)
    prepared_files = []
    for file in files:
        original_name = file.filename or "unnamed"
        content = await file.read()
        validate_upload_file_constraints(original_name, len(content), settings)
        prepared_files.append((file, original_name, content))

    results: List[MediaAsset] = []
    for file, original_name, content in prepared_files:
        raw_ext = os.path.splitext(original_name)[1]
        file_ext_upper = raw_ext.upper()
        mime_type = file.content_type or "application/octet-stream"
        category = classify_media_category(mime_type, raw_ext.lower())

        if sub_path:
            safe_sub_path = sub_path.strip("/")
            tier_folder = config.MEDIA_TIERS.get(final_access_level, "PUBLIC")
            relative_dir = os.path.join(tier_folder, safe_sub_path).replace("\\", "/")
        else:
            relative_dir = media_generate_path(final_access_level, category, user.id)

        abs_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
        safe_makedirs(abs_dir)

        unique_uuid = str(uuid.uuid4())
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            filename = f"{config.PREFIX['IMAGE']}{unique_uuid}{file_ext_upper}"
        else:
            orig_stem = os.path.splitext(original_name)[0] or "document"
            filename = f"{config.PREFIX['DOC']}{unique_uuid[:8]}_{orig_stem}{file_ext_upper}"

        filename = get_unique_filename(abs_dir, filename)
        relative_file_path = os.path.join(relative_dir, filename).replace("\\", "/")
        abs_file_path = os.path.join(abs_dir, filename)

        async with aiofiles.open(abs_file_path, "wb") as f:
            await f.write(content)
        os.chmod(abs_file_path, 0o644)

        file_size = len(content)
        expires_at = (datetime.now() + timedelta(days=keep_days)).isoformat() if auto_expiry else None
        meta_info = {
            "original_name": original_name,
            "has_original": True,
            "original_expires_at": expires_at,
            "original_purged": False,
        }
        thumb_main_path = None

        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            try:
                with Image.open(abs_file_path) as img:
                    meta_info["width"], meta_info["height"] = img.size
                    thumb_dir = os.path.join(abs_dir, config.THUMB_FOLDER_NAME)
                    safe_makedirs(thumb_dir)

                    if img.mode in ("P", "CMYK"):
                        img = img.convert("RGB")

                    sm_cfg = thumb_specs["SM"]
                    sm_img = img.copy()
                    sm_img.thumbnail(sm_cfg["size"], Image.Resampling.LANCZOS)
                    sm_filename = f"{config.PREFIX['THUMB']}{unique_uuid}_{sm_cfg['suffix']}.WEBP"
                    sm_abs_path = os.path.join(thumb_dir, sm_filename)
                    sm_rel_path = os.path.join(relative_dir, config.THUMB_FOLDER_NAME, sm_filename).replace("\\", "/")

                    sm_img.save(sm_abs_path, "WEBP", quality=webp_quality)
                    os.chmod(sm_abs_path, 0o644)

                    meta_info["thumbs"] = {"sm": sm_rel_path}
                    thumb_main_path = sm_rel_path
            except Exception as e:
                logger.error("[Media Error] SM Thumbnail failed: %s", e)

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
            category=category,
        )
        db.add(asset)
        db.flush()

        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            enqueue_task(
                db=db,
                task_type="THUMB_GEN",
                payload={"asset_id": asset.id},
                unique_key=f"thumb-gen-{asset.id}",
                priority=7,
            )

        results.append(asset)

    db.commit()
    for item in results:
        db.refresh(item)
    return results


def isolate_asset_files_sync(asset: MediaAsset, today_str: Optional[str] = None) -> int:
    """폴더 일괄 삭제 시 부모 폴더 리네임 전에 하위 파일·썸네일을 선행 동기 격리합니다."""
    today = today_str or datetime.now().strftime("%Y%m%d")
    abs_file_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
    dir_name = os.path.dirname(abs_file_path)
    base_name = os.path.basename(abs_file_path)
    isolated_count = 0

    if os.path.exists(abs_file_path) and not base_name.startswith(config.PREFIX["DELETE"]):
        new_path = os.path.join(dir_name, f"{config.PREFIX['DELETE']}{today}_{base_name}")
        os.rename(abs_file_path, new_path)
        isolated_count += 1

    thumb_dir = os.path.join(dir_name, config.THUMB_FOLDER_NAME)
    if os.path.exists(thumb_dir):
        uuid_key = os.path.splitext(base_name)[0]
        if uuid_key.startswith(config.PREFIX["IMAGE"]):
            uuid_key = uuid_key[len(config.PREFIX["IMAGE"]):]
        for t_file in os.listdir(thumb_dir):
            if uuid_key and uuid_key in t_file and not t_file.startswith(config.PREFIX["DELETE"]):
                old_t = os.path.join(thumb_dir, t_file)
                new_t = os.path.join(thumb_dir, f"{config.PREFIX['DELETE']}{today}_{t_file}")
                os.rename(old_t, new_t)
                isolated_count += 1

    return isolated_count


def delete_asset(db: Session, asset_id: int, sync_isolate: bool = False) -> bool:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        return False

    asset.is_deleted = True
    asset.deleted_at = datetime.now()

    if sync_isolate:
        isolate_asset_files_sync(asset)
    else:
        enqueue_task(
            db=db,
            task_type="MEDIA_ISOLATE",
            payload={"asset_id": asset.id, "file_path": os.path.join(config.MEDIA_ROOT, asset.file_path)},
            unique_key=f"isolate-{asset.id}",
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
    sub_path: Optional[str] = None,
) -> List[MediaAsset]:
    """
    개인 보관함 자산을 서비스 영역(PUBLIC/PROTECTED)으로 배포 복사합니다.
    - 동적 설정 publish_strip_image_original=True(기본) 시 썸네일 3종만 복사하고,
      False로 변경한 경우 원본 파일까지 함께 물리 복사합니다.
    """
    settings = get_media_settings(db)
    thumb_specs = get_thumb_specs_from_settings(settings)
    webp_quality = int(settings.get("webp_quality", config.WEBP_QUALITY))
    strip_original = bool(settings.get("publish_strip_image_original", True))
    auto_expiry = bool(settings.get("enable_original_auto_expiry", True))
    keep_days = int(settings.get("original_keep_days", 60))
    is_admin = check_is_media_admin(user, db, action="write")

    results: List[MediaAsset] = []
    final_access_level = (
        access_level.upper() if access_level else media_get_access_level(user, app_id, db=db)
    )

    source_assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.id.in_(asset_ids), MediaAsset.is_deleted == False)
        .all()
    )

    for src_asset in source_assets:
        if src_asset.user_id != user.id and not is_admin:
            continue

        src_abs_path = os.path.join(config.MEDIA_ROOT, src_asset.file_path)
        original_name = src_asset.original_name
        raw_ext = os.path.splitext(original_name)[1] or os.path.splitext(src_asset.file_path)[1]
        file_ext_upper = raw_ext.upper()
        mime_type = src_asset.mime_type or "application/octet-stream"
        category = src_asset.category or classify_media_category(mime_type, raw_ext.lower())

        if category != config.MEDIA_CATEGORIES["IMAGE"] and not os.path.exists(src_abs_path):
            logger.warning("[Media Publish] 문서 원본 파일 없음: %s", src_abs_path)
            continue

        if sub_path:
            safe_sub_path = sub_path.strip("/")
            tier_folder = config.MEDIA_TIERS.get(final_access_level, "PUBLIC")
            relative_dir = os.path.join(tier_folder, safe_sub_path).replace("\\", "/")
        else:
            relative_dir = media_generate_path(final_access_level, category, user.id)

        abs_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
        safe_makedirs(abs_dir)

        unique_uuid = str(uuid.uuid4())
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            filename = f"{config.PREFIX['IMAGE']}{unique_uuid}{file_ext_upper}"
        else:
            orig_stem = os.path.splitext(original_name)[0] or "document"
            filename = f"{config.PREFIX['DOC']}{unique_uuid[:8]}_{orig_stem}{file_ext_upper}"

        filename = get_unique_filename(abs_dir, filename)
        relative_file_path = os.path.join(relative_dir, filename).replace("\\", "/")
        abs_file_path = os.path.join(abs_dir, filename)

        thumb_main_path = None

        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            copied_orig = False
            if not strip_original and os.path.exists(src_abs_path):
                shutil.copy2(src_abs_path, abs_file_path)
                os.chmod(abs_file_path, 0o644)
                copied_orig = True

            expires_at = (
                (datetime.now() + timedelta(days=keep_days)).isoformat()
                if (copied_orig and auto_expiry)
                else None
            )
            meta_info = {
                "original_name": original_name,
                "published_from": src_asset.id,
                "has_original": copied_orig,
                "original_expires_at": expires_at,
                "thumbs": {},
            }
            file_size = os.path.getsize(abs_file_path) if copied_orig else (src_asset.file_size or 0)
            thumb_dir = os.path.join(abs_dir, config.THUMB_FOLDER_NAME)
            safe_makedirs(thumb_dir)

            src_dir = os.path.dirname(src_abs_path)
            src_base = os.path.basename(src_asset.file_path)
            src_uuid = src_base.replace(config.PREFIX["IMAGE"], "").split(".")[0]

            copied_thumbs = {}
            for size_key in ("SM", "MD", "LG"):
                cfg = thumb_specs[size_key]
                src_thumb_file = f"{config.PREFIX['THUMB']}{src_uuid}_{cfg['suffix']}.WEBP"
                src_thumb_path = os.path.join(src_dir, config.THUMB_FOLDER_NAME, src_thumb_file)

                if not os.path.exists(src_thumb_path):
                    legacy_path = os.path.join(
                        src_dir, config.LEGACY_THUMB_FOLDER_NAME, f"{src_uuid}_{size_key.lower()}.webp"
                    )
                    if os.path.exists(legacy_path):
                        src_thumb_path = legacy_path

                if os.path.exists(src_thumb_path):
                    dst_thumb_file = f"{config.PREFIX['THUMB']}{unique_uuid}_{cfg['suffix']}.WEBP"
                    dst_thumb_path = os.path.join(thumb_dir, dst_thumb_file)
                    shutil.copy2(src_thumb_path, dst_thumb_path)
                    os.chmod(dst_thumb_path, 0o644)

                    rel_thumb_path = os.path.join(
                        relative_dir, config.THUMB_FOLDER_NAME, dst_thumb_file
                    ).replace("\\", "/")
                    copied_thumbs[size_key.lower()] = rel_thumb_path
                    if size_key == "SM":
                        thumb_main_path = rel_thumb_path

            missing_sizes = [k for k in ("SM", "MD", "LG") if k.lower() not in copied_thumbs]
            if missing_sizes and os.path.exists(src_abs_path):
                try:
                    with Image.open(src_abs_path) as img:
                        meta_info["width"], meta_info["height"] = img.size
                        if img.mode in ("P", "CMYK"):
                            img = img.convert("RGB")
                        for size_key in missing_sizes:
                            cfg = thumb_specs[size_key]
                            t_img = img.copy()
                            t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)
                            t_filename = f"{config.PREFIX['THUMB']}{unique_uuid}_{cfg['suffix']}.WEBP"
                            t_abs = os.path.join(thumb_dir, t_filename)
                            t_rel = os.path.join(
                                relative_dir, config.THUMB_FOLDER_NAME, t_filename
                            ).replace("\\", "/")
                            t_img.save(t_abs, "WEBP", quality=webp_quality)
                            os.chmod(t_abs, 0o644)
                            copied_thumbs[size_key.lower()] = t_rel
                            if size_key == "SM":
                                thumb_main_path = t_rel
                except Exception as e:
                    logger.error("[Media Publish Error] Thumbnail gen from src failed: %s", e)

            if not copied_thumbs and not copied_orig:
                logger.warning("[Media Publish] 이미지 원본 및 썸네일 모두 없음: asset_id=%s", src_asset.id)
                continue

            if not thumb_main_path:
                thumb_main_path = copied_thumbs.get("sm") or copied_thumbs.get("md") or copied_thumbs.get("lg")
            meta_info["thumbs"] = copied_thumbs
        else:
            shutil.copy2(src_abs_path, abs_file_path)
            os.chmod(abs_file_path, 0o644)
            file_size = os.path.getsize(abs_file_path)
            meta_info = {
                "original_name": original_name,
                "published_from": src_asset.id,
                "has_original": True,
            }

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
            category=category,
        )
        db.add(new_asset)
        db.flush()
        results.append(new_asset)

    db.commit()
    for item in results:
        db.refresh(item)
    return results
