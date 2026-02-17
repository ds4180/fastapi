FROM python:3.11-slim

# uv 설치 (파이썬 패키지 매니저)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 의존성 파일 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 의존성 설치 (가상환경 없이 시스템에 직접 설치하여 이미지 크기 줄임)
RUN /bin/uv pip install --system --no-cache -r pyproject.toml

# 소스 코드 복사
COPY . .

# FastAPI 실행 포트
EXPOSE 8000

# uvicorn 실행 (0.0.0.0으로 띄워야 도커 밖에서 접근 가능)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
