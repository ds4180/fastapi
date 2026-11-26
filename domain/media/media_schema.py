"""
[미디어 도메인 요청·정책 Pydantic 스키마 (domain/media/media_schema.py)]
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FolderCreateRequest(BaseModel):
    tier: str
    sub_path: str = ""
    folder_name: str


class BulkActionRequest(BaseModel):
    asset_ids: List[int] = Field(default_factory=list)
    folder_paths: List[str] = Field(default_factory=list)
    tier: str = "PUBLIC"


class PublishRequest(BaseModel):
    asset_ids: List[int]
    app_id: str = "general"
    target_id: Optional[str] = None
    access_level: str = "PUBLIC"
    sub_path: Optional[str] = None


class GCRequest(BaseModel):
    indices: Optional[List[int]] = None
    scheduled_at: Optional[datetime] = None


class MediaSettingsUpdate(BaseModel):
    # 1. 업로드 및 파일 검증 정책
    max_file_size_mb: int = 100
    enforce_extension_whitelist: bool = True
    allowed_extensions: List[str] = Field(default_factory=list)
    default_upload_tier_for_user: str = "PUBLIC"

    # 2. 이미지 변환·썸네일·배포 정책
    webp_quality: int = 85
    thumb_sm_max_px: int = 300
    thumb_md_max_px: int = 900
    thumb_lg_max_px: int = 1920
    publish_strip_image_original: bool = True

    # 3. 수명주기·보관·GC 정책
    enable_original_auto_expiry: bool = True
    original_keep_days: int = 60
    isolation_retention_days: int = 30
    default_gc_indices: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6])

    # 4. 접근 권한·다운로드 거버넌스 정책
    shared_office_min_rank: int = 2
    shared_office_write_min_rank: int = 4
    protected_min_rank: int = 2
    system_serve_min_rank: int = 2
    zip_download_max_files: int = 100

    # 5. 탐색기 기본 UI 정책 및 탭 라벨
    default_view_mode: str = "grid"
    default_recursive_view: bool = True
    tab_labels: Dict[str, str] = Field(default_factory=dict)
