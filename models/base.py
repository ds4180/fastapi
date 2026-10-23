"""
============================================================================
[백엔드 코어 모델 베이스 (models/base.py)]
============================================================================

💡 이 파일의 역할:
시스템의 모든 데이터베이스 테이블이 상속받아야 하는 '최소 공통 척추'입니다.

🌟 신규 앱(플러그인) 개발자를 위한 선물:
어떤 신규 앱이든 `from models.base import Base, TimestampMixin` 만 가져오면,
복잡한 기존 코드를 몰라도 즉시 독립된 새 테이블을 만들고 시스템에 등록할 수 있습니다.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime
from database import Base


class TimestampMixin:
    """
    모든 테이블에서 공통으로 재사용할 수 있는 생성일/수정일 믹스인(Mixin)
    상속받기만 하면 created_at과 updated_at이 자동으로 생성되고 관리됩니다.
    """
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
