import os
import uuid
import aiofiles
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import UploadFile
from PIL import Image
from sqlalchemy.orm import Session
from models import MediaAsset, User
from domain.media import media_config as config

# ==============================================================================
# [Media System Domain Service v1.0]
# ==============================================================================
# 이 서비스는 프로젝트 전역의 미디어 파일 업로드, 저장, 변환 및 DB 등록을 담당합니다.
# 권한별 물리 폴더 격리(PUBLIC/PRIVATE) 및 다중 썸네일 생성이 핵심 기능입니다.
# ==============================================================================

def media_get_access_level(user: User, app_id: str) -> str:
    """
    [권한 인지형 접근 레벨 결정]
    유저의 Rank와 요청한 App의 성격에 따라 파일의 보안 등급을 결정합니다.
    - Rank 4 (전체관리자): 모든 파일 관리 가능
    - 특정 보안 앱: 강제로 PRIVATE 등급 부여
    """
    # 랭크 4 이상 관리자거나 특정 공용 앱인 경우
    if user.rank() >= 4:
        return "PUBLIC"
    
    # 보안이 필요한 특정 앱의 경우 (예: 개인정보, 결제서류) PRIVATE 강제
    if app_id in ["identity", "secure_doc"]:
        return "PRIVATE"
        
    return "PUBLIC"

def media_generate_path(access_level: str, category: str, user_id: int) -> str:
    """
    [물리 저장 경로 자동 생성]
    media_config의 정책에 따라 계층화된 경로를 생성합니다.
    - 예 (PUBLIC): public/image/2026/04/11/
    - 예 (PRIVATE): private/user_123/document/2026/04/11/
    """
    now = datetime.now()
    date_path = now.strftime("%Y/%m/%d")
    tier_folder = config.MEDIA_TIERS.get(access_level, "public")
    
    if access_level == "PRIVATE":
        # ⚠️ 개인 보안 영역: 유저 ID(user_{id}) 폴더를 중간에 끼워 넣어 물리적으로 격리
        return os.path.join(tier_folder, f"user_{user_id}", category, date_path)
    
    # 일반 공개 영역
    return os.path.join(tier_folder, category, date_path)

async def media_process_upload(
    db: Session,
    user: User,
    files: List[UploadFile],
    app_id: str = "general",
    target_id: str = None,
    access_level: Optional[str] = None,
    sub_path: Optional[str] = None
) -> List[MediaAsset]:
    """
    [미디어 통합 업로드 파이프라인]
    1. 유저 권한에 따른 보안 레벨(PUBLIC/PRIVATE) 결정 (매개변수 우선)
    2. 운영체제 독립적인 물리 경로 생성 및 폴더 확보 (sub_path 우선)
    3. 원본 파일 저장 (중복 방지를 위해 UUID 파일명 사용)
    4. 이미지의 경우 Pillow를 사용하여 다중 WebP 썸네일(SM, MD, LG) 자동 생성
    5. MediaAsset 모델을 통한 DB 영속화 (정적 서빙을 위한 상대 경로 저장)
    """
    results = []
    # 매개변수로 전달된 access_level이 있으면 그것을 사용, 없으면 자동 결정
    final_access_level = access_level.upper() if access_level else media_get_access_level(user, app_id)

    for file in files:
        # --- 1. 파일 기본 정보 추출 ---
        original_name = file.filename
        file_ext = os.path.splitext(original_name)[1].lower()
        mime_type = file.content_type or "application/octet-stream"
        
        # --- 2. 카테고리 판별 (이미지 vs 일반문서) ---
        if mime_type.startswith("image/"):
            category = config.MEDIA_CATEGORIES["IMAGE"]
        else:
            category = config.MEDIA_CATEGORIES["DOCUMENT"]
            
        # --- 3. 물리 저장 경로 확정 ---
        if sub_path:
            # 전달된 sub_path가 있으면 티어 폴더와 결합하여 사용
            tier_folder = config.MEDIA_TIERS.get(final_access_level, "public")
            relative_dir = os.path.join(tier_folder, sub_path.strip("/")).replace("\\", "/")
        else:
            # 기본 날짜 기반 경로 생성
            relative_dir = media_generate_path(final_access_level, category, user.id)
            
        abs_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
        os.makedirs(abs_dir, exist_ok=True) 
        
        # --- 4. 고유 파일명 생성 및 저장 ---
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}{file_ext}"
        relative_file_path = os.path.join(relative_dir, filename).replace("\\", "/")
        abs_file_path = os.path.join(abs_dir, filename)

        content = await file.read()
        async with aiofiles.open(abs_file_path, "wb") as f:
            await f.write(content)
        
        file_size = len(content)
        meta_info = {"original_name": original_name}
        thumb_main_path = None

        # --- 5. 이미지 특화 처리: 다중 WebP 썸네일 프로세싱 ---
        if category == config.MEDIA_CATEGORIES["IMAGE"]:
            try:
                with Image.open(abs_file_path) as img:
                    meta_info["width"], meta_info["height"] = img.size
                    
                    # 썸네일 전용 서브 폴더 생성 (thumbnails/)
                    thumb_dir = os.path.join(abs_dir, "thumbnails")
                    os.makedirs(thumb_dir, exist_ok=True)
                    
                    if img.mode in ("P", "CMYK"):
                        img = img.convert("RGB")
                    
                    thumbs_data = {}
                    for key, cfg in config.MEDIA_THUMB_CONFIG.items():
                        t_img = img.copy()
                        t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)
                        
                        t_filename = f"{unique_id}_{cfg['suffix']}.webp"
                        t_abs_path = os.path.join(thumb_dir, t_filename)
                        t_rel_path = os.path.join(relative_dir, "thumbnails", t_filename).replace("\\", "/")
                        
                        t_img.save(t_abs_path, "WEBP", quality=config.WEBP_QUALITY)
                        thumbs_data[key.lower()] = t_rel_path
                        
                        if key == "MD":
                            thumb_main_path = t_rel_path
                    
                    meta_info["thumbs"] = thumbs_data
            except Exception as e:
                print(f"[Media Error] Thumbnail processing failed: {e}")

        # --- 6. MediaAsset 모델 생성 및 DB 저장 ---
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
        results.append(asset)

    db.commit() 
    for asset in results:
        db.refresh(asset) 
        
    return results

def delete_asset(db: Session, asset_id: int):
    """
    [자산 소프트 삭제 및 물리 격리]
    1. DB에서 해당 자산의 is_deleted 플래그를 True로 변경
    2. 실제 물리 파일명 앞에 'deleted_' 접두어를 붙여 접근 차단 및 격리
    """
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        return False
    
    asset.is_deleted = True
    asset.deleted_at = datetime.now()
    
    # 실제 물리 파일 격리 처리 (파일명 변경)
    abs_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
    if os.path.exists(abs_path):
        dir_name = os.path.dirname(abs_path)
        base_name = os.path.basename(abs_path)
        new_path = os.path.join(dir_name, f"deleted_{base_name}")
        try:
            os.rename(abs_path, new_path)
            # 썸네일도 있다면 함께 격리 (생략 가능하나 완벽을 기함)
            if asset.thumbnail_path:
                t_abs_path = os.path.join(config.MEDIA_ROOT, asset.thumbnail_path)
                if os.path.exists(t_abs_path):
                    os.rename(t_abs_path, os.path.join(os.path.dirname(t_abs_path), f"deleted_{os.path.basename(t_abs_path)}"))
        except Exception as e:
            print(f"[Media Error] Physical isolation failed: {e}")
            
    db.commit()
    return True
