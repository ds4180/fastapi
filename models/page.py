"""
============================================================================
[독립형 고정 콘텐츠 페이지 모델 (models/page.py)]
============================================================================

💡 이 파일의 역할:
회사 소개, 이용 안내 등 관리자가 TipTap 리치 에디터로 자유롭게 작성하는
독립형 웹 페이지(Page) 모델을 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from models.base import Base


class Page(Base):
    """독립형 고정 콘텐츠 페이지 엔진 모델"""
    __tablename__ = "page"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False) # URL 경로용 고유 식별자
    title = Column(String, nullable=False)                         # 페이지 제목
    content = Column(Text, nullable=True)                          # HTML/텍스트 본문
    content_json = Column(JSONB, nullable=False)                   # TipTap 에디터 JSON 데이터
    
    status = Column(String, default="DRAFT")                       # DRAFT, PUBLISHED
    is_active = Column(Boolean, default=True)                      # 활성 여부
    min_rank = Column(Integer, default=0)                          # 열람 가능 최소 등급
    redirect_url = Column(String, nullable=True)                  # 외부 리다이렉트 URL
    
    is_deleted = Column(Boolean, default=False, nullable=False)    # 논리 삭제 플래그
    delete_date = Column(DateTime, nullable=True)
    
    published_at = Column(DateTime, nullable=False, default=datetime.now) # 게시 시작 시각
    expired_at = Column(DateTime, nullable=True)                         # 게시 종료 시각 (선택)
    
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
