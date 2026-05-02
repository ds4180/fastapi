import os

# ==============================================================================
# [Media System Global Configuration v3.1]
# ==============================================================================
# 이 파일의 설정은 시스템 전역 미디어 자산의 저장 및 네이밍 규칙을 결정합니다.
# ==============================================================================

# 1. 물리 저장소 루트 (컨테이너 내부 경로)
MEDIA_ROOT = os.getenv("UPLOAD_DIR", "/app/uploads")

# 2. 접근 계층(Tier) 정의 - 폴더명은 반드시 대문자
MEDIA_TIERS = {
    "PUBLIC": "PUBLIC",
    "PROTECTED": "PROTECTED",
    "PRIVATE": "PRIVATE",
    "SYSTEM": "SYSTEM"
}

# 3. 미디어 카테고리 정의
MEDIA_CATEGORIES = {
    "IMAGE": "image",
    "DOCUMENT": "document",
    "ARCHIVE": "archive"
}

# 4. 네이밍 접두어 (Prefix) - v3.1 표준
PREFIX = {
    "IMAGE": "IMG_",
    "DOC": "DOC_",
    "THUMB": "TMB_",
    "DELETE": "DEL_"
}

# 5. 썸네일 설정
THUMB_FOLDER_NAME = "THUMB" # 기존 thumbnails에서 THUMB로 변경
WEBP_QUALITY = 85

# 썸네일 규격 및 파일명 접미어 (Suffix) - 대문자 고정
MEDIA_THUMB_CONFIG = {
    "SM": {"size": (300, 300), "suffix": "SM"}, # 리스트용
    "MD": {"size": (900, 900), "suffix": "MD"}, # 상세페이지용
    "LG": {"size": (1920, 1920), "suffix": "LG"} # 원본급 확대용
}

# 6. 기타 설정
MAX_FILE_SIZE = 100 * 1024 * 1024 # 100MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.docx', '.xlsx', '.zip'}
