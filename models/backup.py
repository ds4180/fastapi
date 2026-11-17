"""
============================================================================
[물리 백업 출력 이력 모델 (models/backup.py)]
============================================================================

💡 역할:
도메인별 물리적 백업(인쇄 / PDF 저장) 회차, 기간, 마지막 출력 레코드 ID(체크포인트),
연번, 무결성 체크섬을 저장하는 이력 원장 테이블입니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from models.base import Base, JSONType


class BackupPrintLog(Base):
    __tablename__ = "backup_print_logs"

    id = Column(Integer, primary_key=True)
    app_id = Column(String(100), nullable=False, index=True)
    app_name = Column(String(100), nullable=True)
    mode = Column(String(30), nullable=False, default="CUSTOM")  # CONTINUE | HALF_YEAR | CUSTOM
    start_date = Column(String(20), nullable=True)
    end_date = Column(String(20), nullable=True)
    last_record_id = Column(Integer, nullable=True)
    last_seq_no = Column(Integer, nullable=False, default=0)
    record_count = Column(Integer, nullable=False, default=0)
    fields = Column(JSONType, nullable=False, default=list)
    checksum = Column(String(64), nullable=True)
    printed_by = Column(String(100), nullable=True)
    printed_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
