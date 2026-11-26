from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from core.config import settings

# 📌 중앙 설정소(core/config.py)에서 검증된 PostgreSQL 접속 주소를 안전하게 가져옵니다.
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# 💡 [DB 커넥션 풀 안정성 설정]:
# - pool_size / max_overflow / pool_timeout / pool_recycle은 .env 또는 docker-compose environment로 언제든 조절 가능.
# - 기본값(pool_size=10, max_overflow=20 -> 최대 30개)은 PostgreSQL max_connections(100) 대비 안전한 탄력 한도.
# - pool_pre_ping=True: 커넥션을 사용할 때 DB 연결이 살아있는지 먼저 확인하여 끊어진 유휴 연결 에러(500)를 자동 복구합니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 🏛️ [감사로그 리스너 등록]: AuditMixin을 상속받은 모델의 변경사항(Diff-Patch)을 자동 캡처
from core.audit_listener import setup_audit_listeners
setup_audit_listeners()

def get_db():
    """
    FastAPI 요청마다 DB 세션을 생성하고 작업 완료 시 자동으로 닫아주는 의존성 함수
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

        