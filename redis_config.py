import redis
from core.config import settings

# 📌 중앙 설정소(core/config.py)에서 검증된 Redis 접속 정보를 가져옵니다.
REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_PASSWORD = settings.REDIS_PASSWORD

# Redis 클라이언트 객체 생성
# decode_responses=True: Redis 데이터를 파이썬 문자열(str)로 자동 디코딩합니다.
rd = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=0,
    decode_responses=True
)

def get_redis():
    """
    FastAPI 라우터에서 Depends(get_redis) 형태로 의존성 주입할 때 사용합니다.
    """
    return rd
