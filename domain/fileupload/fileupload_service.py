import os
import uuid
import aiofiles
import io
from fastapi import UploadFile
from typing import List, Dict
from PIL import Image

async def save_upload_files(files: List[UploadFile]) -> List[Dict[str, str]]:
    """
    여러 파일을 서버에 저장하고 메타데이터 리스트를 반환합니다.
    """
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    uploaded_info = []
    
    for file in files:
        # 1. 고유 파일명 생성 (UUID)
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # 2. 파일 데이터 읽기 및 저장
        # 비동기 파일 읽기 (Pillow와 공유하기 위해 메모리에 임시 저장)
        content = await file.read()
        
        async with aiofiles.open(file_path, "wb") as out_file:
            await out_file.write(content)
        
        # 3. 썸네일 생성 (이미지인 경우 무조건 생성, 900x900 제한)
        thumbnail_filename = None
        if file.content_type and file.content_type.startswith("image/"):
            try:
                # 썸네일 저장 폴더 생성 (uploads/thumbnails)
                thumb_dir = os.path.join(upload_dir, "thumbnails")
                os.makedirs(thumb_dir, exist_ok=True)
                
                thumbnail_filename = f"thumb_{unique_filename}"
                thumb_path = os.path.join(thumb_dir, thumbnail_filename)
                
                # Pillow를 이용한 이미지 리사이징
                with Image.open(io.BytesIO(content)) as img:
                    # RGB 모드로 변환 (RGBA인 경우 JPEG 저장 시 오류 방지)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                        
                    img.thumbnail((900, 900))
                    # 퀄리티를 유지하며 저장
                    img.save(thumb_path, "JPEG", quality=85)
            except Exception as e:
                print(f"Thumbnail creation failed for {file.filename}: {e}")
                thumbnail_filename = None

        # 4. 메타데이터 구성
        uploaded_info.append({
            "original_name": file.filename,
            "filename": unique_filename,
            "thumbnail_filename": thumbnail_filename,
            "url": f"/uploads/{unique_filename}",
            "thumbnail_url": f"/uploads/thumbnails/{thumbnail_filename}" if thumbnail_filename else None
        })
        
    return uploaded_info

def rename_to_deleted(filename: str, thumbnail_filename: str = None):
    """
    파일 이름 앞에 'deleted_'를 붙여 나중에 크론탭 등으로 삭제할 수 있도록 격리합니다.
    """
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    thumb_dir = os.path.join(upload_dir, "thumbnails")

    # 1. 원본 파일 이름 변경
    if filename:
        try:
            old_path = os.path.join(upload_dir, filename)
            new_path = os.path.join(upload_dir, f"deleted_{filename}")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
        except Exception as e:
            print(f"File rename failed: {e}")

    # 2. 썸네일 파일 이름 변경
    if thumbnail_filename:
        try:
            old_thumb_path = os.path.join(thumb_dir, thumbnail_filename)
            new_thumb_path = os.path.join(thumb_dir, f"deleted_{thumbnail_filename}")
            if os.path.exists(old_thumb_path):
                os.rename(old_thumb_path, new_thumb_path)
        except Exception as e:
            print(f"Thumbnail rename failed: {e}")
