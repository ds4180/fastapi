from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# PostgreSQL 접속 주소. "사용자:비밀번호@호스트:포트/데이터베이스명" 형식입니다.
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg://bus1942:bus1942@localhost/bus1942"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
# SQLite 데이터베이스

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

        