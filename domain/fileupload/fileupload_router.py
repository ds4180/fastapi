from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import List
import os
import uuid
import aiofiles
import tempfile
import shutil

from domain.fileupload import fileupload_service

# APIRouter를 생성하여 파일 업로드 관련 API 엔드포인트들을 그룹화합니다.
router = APIRouter(
    prefix="/uploadfiles",
)

@router.post("")
async def upload_files(files: List[UploadFile] = File(...)):
    """
    여러 파일을 비동기적으로 업로드하고 상세 정보 리스트를 반환합니다.
    """
    try:
        uploaded_info = await fileupload_service.save_upload_files(files)
        return uploaded_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
