from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from core.config import settings

# 📌 중앙 설정소(core/config.py)에서 검증된 PostgreSQL 접속 주소를 안전하게 가져옵니다.
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """
    FastAPI 요청마다 DB 세션을 생성하고 작업 완료 시 자동으로 닫아주는 의존성 함수
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

        