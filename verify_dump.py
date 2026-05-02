import os
import re
from sqlalchemy import create_engine, text

dump_file = "/app/cloud_ready_dump.sql"  # 컨테이너 내 마운트 경로 또는 로컬 경로 맞춰야함
# test/ 디렉토리가 /app에 마운트되어 있으니, cloud_ready_dump.sql 을 test/ 로 복사해서 컨테이너가 읽게 함
dump_file = "/app/cloud_ready_dump.sql"

# 1. 덤프 파일 내 테이블별 데이터 행(row) 수 계산
dump_counts = {}
current_table = None
count = 0

try:
    with open(dump_file, "r") as f:
        for line in f:
            if line.startswith("COPY "):
                match = re.search(r"COPY public\.([a-zA-Z0-9_]+) ", line)
                if match:
                    current_table = match.group(1)
                    count = 0
            elif current_table and line.strip() == "\\.":
                dump_counts[current_table] = count
                current_table = None
            elif current_table:
                count += 1
except FileNotFoundError:
    print("Error: /app/cloud_ready_dump.sql not found inside container.")
    exit(1)

print(f"{'테이블 이름':<30} | {'로컬 DB 데이터':<20} | {'백업 파일 데이터':<20} | {'일치 여부'}")
print("-" * 90)

# 2. 로컬 DB 쿼리 (FastAPI의 SQLAlchemy engine 사용)
from database import engine

try:
    with engine.connect() as conn:
        # public 스키마의 테이블 목록
        result = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';"))
        tables = [row[0] for row in result]
        
        for table in sorted(tables):
            if table == 'alembic_version': continue
            
            count_result = conn.execute(text(f"SELECT COUNT(*) FROM public.{table};"))
            db_count = count_result.fetchone()[0]
            
            dump_count = dump_counts.get(table, 0)
            match = "✅ 일치" if db_count == dump_count else "❌ 불일치!!"
            print(f"{table:<30} | {db_count:<25} | {dump_count:<20} | {match}")
except Exception as e:
    print("DB 조회 중 에러 발생:", e)
