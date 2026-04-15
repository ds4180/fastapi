import os

# ==============================================================================
# [Media System Global Configuration v1.0]
# ==============================================================================
# ⚠️ 중요: 이 파일의 설정 값들은 프론트엔드의 `svelte5/src/lib/config/media.js`와
# 반드시 1:1로 일치해야 합니다. 폴더명이나 키값이 불일치할 경우 이미지 엑박이나
# 404 에러가 발생하며, Nginx 프록시 설정이 깨질 수 있습니다.
# ==============================================================================

# 1. 파일 저장 루트 경로 (Docker 환경변수 참조)
# 컨테이너 내부: /app/uploads, 호스트: .../user_uploads
MEDIA_ROOT = os.getenv("UPLOAD_DIR", "uploads")

# 2. 접근 계층(Tier) 정의: Nginx 프록시 분기 및 보안 권한의 기준이 됨
# - PUBLIC: Nginx가 직접 서빙 (성능 최적화)
# - PROTECTED: 세션 체크 후 서빙 (공유 문서)
# - PRIVATE: 본인/관리자 전용 (사용자 ID 기반 물리 격리)
# - SYSTEM: 시스템 설정 및 관리자 전용 자산
MEDIA_TIERS = {
    "PUBLIC": "public",
    "PROTECTED": "protected",
    "PRIVATE": "private",
    "SYSTEM": "system"
}

# 3. 미디어 카테고리: 폴더 구조의 2단계를 결정 (예: public/image/...)
MEDIA_CATEGORIES = {
    "IMAGE": "image",
    "DOCUMENT": "document",
    "ARCHIVE": "archive"
}

# 4. 다중 썸네일 생성 정책 (Windows 탐색기 스타일 대응)
# - SM (Small): 리스트/그리드 뷰 (150px)
# - MD (Medium): 상세페이지 미리보기 (600px)
# - LG (Large): 고해상도 뷰어/라이트박스 (1200px)
# ⚠️ 주의: 접두어(suffix) 변경 시 프론트엔드의 getThumbnailUrl 로직과 맞춰야 함
MEDIA_THUMB_CONFIG = {
    "SM": {"size": (150, 150), "suffix": "sm"},
    "MD": {"size": (600, 600), "suffix": "md"},
    "LG": {"size": (1200, 1200), "suffix": "lg"}
}

# 5. 이미지 처리 품질 설정
WEBP_QUALITY = 85  # 용량 대비 화질 최적화 값 (80~90 권장)
