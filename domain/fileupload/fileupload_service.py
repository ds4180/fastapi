import os
import uuid
import shutil
import aiofiles
import io
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from fastapi import UploadFile
from PIL import Image

# 기본 설정
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
TEMP_IMG_DIR = os.path.join(UPLOAD_DIR, "tmp", "img")
TEMP_FILE_DIR = os.path.join(UPLOAD_DIR, "tmp", "file")

def ensure_temp_dirs():
    """임시 디렉토리 생성 확인"""
    try:
        os.makedirs(TEMP_IMG_DIR, exist_ok=True)
        os.makedirs(TEMP_FILE_DIR, exist_ok=True)
    except Exception as e:
        print(f"Error creating temp directories: {e}")

async def save_upload_files(files: List[UploadFile]) -> List[Dict[str, str]]:
    """1단계: 임시 저장"""
    ensure_temp_dirs()
    uploaded_info = []

    for file in files:
        file_extension = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        is_image = False
        if file.content_type:
            is_image = file.content_type.startswith("image/")
        else:
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
            is_image = file_extension in image_extensions

        temp_dir = TEMP_IMG_DIR if is_image else TEMP_FILE_DIR
        temp_path = os.path.join(temp_dir, unique_filename)

        try:
            content = await file.read()
            async with aiofiles.open(temp_path, "wb") as out_file:
                await out_file.write(content)
            
            category_dir = "img" if is_image else "file"
            temp_relative_path = f"tmp/{category_dir}/{unique_filename}"
            
            uploaded_info.append({
                "original_name": file.filename,
                "filename": temp_relative_path,
                "is_image": is_image,
                "content_type": file.content_type
            })
        except Exception as e:
            print(f"Failed to save temp file: {e}")
            raise e
        
    return uploaded_info

def finalize_uploads(image_files: List[Dict]) -> List[Dict]:
    """2단계: 최종 이동 및 WebP 썸네일 생성"""
    final_files = []
    now = datetime.now()
    date_path = os.path.join(str(now.year), str(now.month).zfill(2), str(now.day).zfill(2))
    
    for file_data in image_files:
        full_filename = file_data['filename']
        
        if not full_filename.startswith("tmp/"):
            final_files.append(file_data)
            continue

        filename = os.path.basename(full_filename)
        file_extension = os.path.splitext(filename)[1].lower()
        is_image = file_data.get('is_image', file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'])
        
        temp_dir = TEMP_IMG_DIR if is_image else TEMP_FILE_DIR
        temp_path = os.path.join(temp_dir, filename)
        
        if not os.path.exists(temp_path):
            final_files.append(file_data)
            continue

        category = "img" if is_image else "file"
        final_subdir = os.path.join(category, date_path)
        final_dir = os.path.join(UPLOAD_DIR, final_subdir)
        os.makedirs(final_dir, exist_ok=True)
        
        final_path = os.path.join(final_dir, filename)
        
        try:
            shutil.move(temp_path, final_path)
            
            thumbnail_filename = None
            if is_image:
                try:
                    thumb_subdir = os.path.join(final_subdir, "thumbnails")
                    thumb_dir = os.path.join(UPLOAD_DIR, thumb_subdir)
                    os.makedirs(thumb_dir, exist_ok=True)

                    # WebP 형식으로 변경
                    thumbnail_filename = f"thumb_{os.path.splitext(filename)[0]}.webp"
                    thumb_path = os.path.join(thumb_dir, thumbnail_filename)

                    with Image.open(final_path) as img:
                        # WebP는 RGBA를 지원하므로 RGB 변환이 필수는 아니나, 
                        # 일관성을 위해 투명도가 없는 경우 RGB로 처리하면 용량이 더 줄어듭니다.
                        if img.mode in ("P", "CMYK"):
                            img = img.convert("RGB")
                        
                        # 1200px 크기는 대화면에서도 선명하게 보일 만큼 고화질입니다.
                        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                        # WebP 저장 (품질 80, method 6은 압축률 최적화)
                        img.save(thumb_path, "WEBP", quality=80, method=6)
                    print(f"Created high-res WebP thumbnail: {thumb_path}")
                except Exception as e:
                    print(f"Thumbnail error: {e}")

            final_files.append({
                "filename": f"{category}/{date_path}/{filename}".replace("\\", "/"),
                "original_name": file_data['original_name'],
                "thumbnail_filename": f"{category}/{date_path}/thumbnails/{thumbnail_filename}".replace("\\", "/") if thumbnail_filename else None,
                "is_image": is_image
            })
        except Exception as e:
            print(f"Error finalizing: {e}")
            final_files.append(file_data)
        
    return final_files

def rename_to_deleted(relative_path: str, thumbnail_relative_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """3단계: delete_ 접두어 추가"""
    def rename_file(rel_path: str) -> str:
        if not rel_path:
            return rel_path
        
        src_path = os.path.join(UPLOAD_DIR, rel_path)
        if os.path.exists(src_path):
            directory = os.path.dirname(src_path)
            filename = os.path.basename(src_path)
            if not filename.startswith("delete_"):
                new_filename = f"delete_{filename}"
                dest_path = os.path.join(directory, new_filename)
                try:
                    os.rename(src_path, dest_path)
                    return os.path.join(os.path.dirname(rel_path), new_filename).replace("\\", "/")
                except: pass
        return rel_path

    return rename_file(relative_path), rename_file(thumbnail_relative_path)
