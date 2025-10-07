from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import List
import os
import uuid
import aiofiles
import tempfile
import shutil

# APIRouter를 생성하여 파일 업로드 관련 API 엔드포인트들을 그룹화합니다.
# prefix="/api/uploadfiles" 설정을 통해 이 라우터에 포함된 모든 경로 앞에 자동으로 /api/uploadfiles가 붙게 됩니다.
router = APIRouter(
    prefix="/api/uploadfiles",
)

# POST 요청을 처리하는 API 엔드포인트를 정의합니다.
# 클라이언트는 이 경로로 파일을 포함한 POST 요청을 보낼 수 있습니다.
@router.post("/")
async def upload_files(files: List[UploadFile] = File(...)):
    """
    여러 개의 파일을 비동기적으로 업로드하고 서버에 저장합니다.

    - Args:
        - files (List[UploadFile]): 클라이언트로부터 업로드된 파일들의 리스트입니다.
                                     FastAPI는 'multipart/form-data' 요청을 분석하여 이 파라미터에 주입합니다.

    - Raises:
        - HTTPException(500): 파일 저장 중 오류가 발생하면 500 상태 코드와 함께 에러 메시지를 반환합니다.

    - Returns:
        - dict: 업로드 성공 시, 성공 메시지와 업로드된 파일 수를 포함하는 JSON 객체를 반환합니다.
    """
    # 1. 업로드된 파일을 저장할 디렉터리를 지정하고, 디렉터리가 존재하지 않으면 생성합니다.
    #    `exist_ok=True` 옵션은 디렉터리가 이미 존재해도 오류를 발생시키지 않습니다.
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # 2. 클라이언트가 보낸 모든 파일에 대해 반복 작업을 수행합니다.
    for file in files:
        try:
            # 3. 파일 이름 충돌을 방지하기 위해 UUID를 사용하여 고유한 파일명을 생성합니다.
            #    원본 파일의 확장자를 유지합니다. (예: 'my-image.jpg' -> '...-....-....-....jpg')
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)
            
            # 4. `aiofiles`를 사용하여 파일을 비동기적으로 씁니다. (Non-blocking I/O)
            #    - `async with` 구문은 파일 핸들을 안전하게 열고 닫습니다.
            #    - 대용량 파일을 효율적으로 처리하기 위해 1MB 청크(chunk) 단위로 파일을 읽고 씁니다.
            #      이렇게 하면 서버 메모리가 한 번에 과도하게 사용되는 것을 방지할 수 있습니다.
            async with aiofiles.open(file_path, "wb") as out_file:
                while content := await file.read(1024 * 1024):  # 1MB씩 읽기
                    await out_file.write(content)
        except Exception as e:
            # 5. 파일 저장 과정에서 예외가 발생하면, 서버 로그에 에러를 기록하고
            #    클라이언트에게 500 Internal Server Error 응답을 보냅니다.
            raise HTTPException(status_code=500, detail=f"Error uploading file: {file.filename}")
            
    # 6. 모든 파일이 성공적으로 업로드되면, 클라이언트에게 성공 메시지를 반환합니다.
    return {"message": f"Successfully uploaded {len(files)} files"}
