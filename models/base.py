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
from typing import Set
from sqlalchemy import Column, DateTime, Integer
from database import Base


class TimestampMixin:
    """
    모든 테이블에서 공통으로 재사용할 수 있는 생성일/수정일 믹스인(Mixin)
    상속받기만 하면 created_at과 updated_at이 자동으로 생성되고 관리됩니다.
    """
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class AuditMixin:
    """
    [도메인 앱 자동 감사 추적 믹스인 (AuditMixin)]
    
    💡 역할:
    도메인 엔티티 모델(배차, 차량, 휴무, 게시판 등)이 이 믹스인을 상속받기만 하면:
    1. 개발자가 로깅 코드를 일일이 작성하지 않아도, SQLAlchemy 커밋 시
       어떤 컬럼이 수정 전(from)에서 수정 후(to)로 바뀌었는지 필드 단위의 Diff-Patch를
       코어 리스너가 100% 자동으로 캡처하여 audit_logs 테이블에 보존합니다.
    2. 데이터 수정 시마다 version 번호가 1씩 자동 증가하여 변경 순서를 완벽히 보장합니다.
    
    🌟 사용 예시:
    class Dispatch(Base, TimestampMixin, AuditMixin):
        __tablename__ = "dispatch"
        __audit_app_id__ = "dispatch" # 이 모델이 속한 앱 식별자
        __audit_exclude_fields__ = {"updated_at", "created_at"} # Diff 추적 제외 필드
    """
    __audit_app_id__: str = "system"
    __audit_exclude_fields__: Set[str] = {"updated_at", "created_at"}

    version = Column(Integer, default=1, nullable=False)
