import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# PostgreSQL 접속 주소. 환경 변수가 없으면 기본값을 사용합니다.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+psycopg://lee:1234@db/bus_db"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
# SQLite 데이터베이스

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

        