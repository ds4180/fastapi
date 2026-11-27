from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from typing import List

from domain.fileupload import fileupload_service
from domain.user.user_router import get_current_user
from models import User

# APIRouter를 생성하여 파일 업로드 관련 API 엔드포인트들을 그룹화합니다.
router = APIRouter(
    prefix="/uploadfiles",
)

@router.post("")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    여러 파일을 비동기적으로 업로드하고 상세 정보 리스트를 반환합니다. (로그인 인증 필수)
    """
    try:
        uploaded_info = await fileupload_service.save_upload_files(files)
        return uploaded_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
