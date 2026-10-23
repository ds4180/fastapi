"""
============================================================================
[시스템 전역 미디어 자산 관리 모델 (models/media.py)]
============================================================================

💡 이 파일의 역할:
업로드된 이미지, 문서, 압축 파일 등의 물리적 경로와 권한(PUBLIC, PROTECTED, PRIVATE),
썸네일 메타데이터를 관리하는 중앙 파일 모델(MediaAsset)을 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base


class MediaAsset(Base):
    """시스템 전역 미디어 자산 관리 모델"""
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 접근 레벨: PUBLIC(공개), PROTECTED(로그인 필수), PRIVATE(소유자 전용), SYSTEM
    access_level = Column(String(20), default="PUBLIC")
    app_id = Column(String(50), index=True)             # 'board', 'profile', 'admin' 등
    target_id = Column(String(100), index=True)         # 연결된 대상 ID
    
    # 파일 물리 정보
    original_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)     # 실제 물리 저장 상대 경로
    thumbnail_path = Column(String(500), nullable=True)  # 기본 썸네일 경로
    
    # 이미지 해상도 및 다중 썸네일 규격 ({ "width": 1024, "thumbs": {"sm": "...", "md": "..."} })
    meta_info = Column(JSONB, default=dict)
    
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    category = Column(String(20))                       # 'image', 'document', 'archive'
    
    is_deleted = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="media_assets")
