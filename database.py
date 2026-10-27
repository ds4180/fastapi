from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from core.config import settings

# 📌 중앙 설정소(core/config.py)에서 검증된 PostgreSQL 접속 주소를 안전하게 가져옵니다.
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# 💡 [DB 커넥션 풀 안정성 설정]:
# - 풀 개수(pool_size=5, max_overflow=10)는 메모리 점유와 컨텍스트 스위칭 방지를 위해 기본값을 현행 유지합니다.
# - pool_pre_ping=True: 커넥션을 사용할 때 DB 연결이 살아있는지 먼저 확인하여 끊어진 유휴 연결 에러(500)를 자동 복구합니다.
# - pool_recycle=1800: 30분(1800초)마다 오래된 커넥션을 안전하게 갱신하여 장시간 구동 시 메모리 누수를 방지합니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)
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

        