import os

# ==============================================================================
# [Media System Physical & Default Constants (domain/media/media_config.py)]
# ==============================================================================
# 물리 디스크 구조·접두어·예약어 등 불변 규격 상수와 동적 정책의 초기 기본값을 정의합니다.
# 운영 중 변경 가능한 비즈니스 정책은 media_policy_service (SystemConfig: media_settings)에서 조회합니다.
# ==============================================================================

# 1. 물리 저장소 루트 (컨테이너 내부 경로)
MEDIA_ROOT = os.getenv("UPLOAD_DIR", "/app/uploads")

# 2. 접근 계층(Tier) 정의 - 폴더명은 반드시 대문자
MEDIA_TIERS = {
    "PUBLIC": "PUBLIC",
    "PROTECTED": "PROTECTED",
    "PRIVATE": "PRIVATE",
    "SYSTEM": "SYSTEM",
}

# 3. 미디어 카테고리 정의
MEDIA_CATEGORIES = {
    "IMAGE": "image",
    "DOCUMENT": "document",
    "ARCHIVE": "archive",
}

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".7z", ".rar"}

# 4. 네이밍 접두어 (Prefix) - 숨김/격리는 '.' 접두어 적용
PREFIX = {
    "IMAGE": "IMG_",
    "DOC": "DOC_",
    "THUMB": "TMB_",
    "DELETE": ".DEL_",
    "DELETE_ORIG": ".DEL_ORIG_",
}

# 5. 썸네일 폴더 및 예약어 SSOT
THUMB_FOLDER_NAME = "THUMB"
LEGACY_THUMB_FOLDER_NAME = "thumbnails"

RESERVED_FOLDER_NAMES = {"THUMB", "THUMBNAILS", "TMP"}
RESERVED_ROOT_SUBFOLDERS = {"PUBLIC", "PROTECTED", "PRIVATE", "SYSTEM", "USERS", "GLOBAL"}
RESERVED_FOLDER_PREFIXES = (".", "DEL_")

# 6. 동적 설정 폴백용 기본 상수 (하위 호환 유지)
WEBP_QUALITY = 85
MEDIA_THUMB_CONFIG = {
    "SM": {"size": (300, 300), "suffix": "SM"},
    "MD": {"size": (900, 900), "suffix": "MD"},
    "LG": {"size": (1920, 1920), "suffix": "LG"},
}
MAX_FILE_SIZE = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".docx", ".xlsx", ".zip", ".hwp", ".txt", ".csv",
}
