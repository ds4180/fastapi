import os
import redis

# 환경 변수에서 설정 로드 (도커 컴포즈의 environment 설정과 일치시킵니다)
REDIS_HOST = os.getenv("REDIS_HOST", "redis") # 도커 네트워크 안에서는 서비스 이름인 'redis'로 접근합니다.
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "1234")

# Redis 클라이언트 객체 생성
# decode_responses=True: 바이트 데이터를 자동으로 파이썬 문자열로 변환해줍니다.
rd = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=0,
    decode_responses=True
)

def get_redis():
    """
    FastAPI의 Depends(get_redis) 형태로 사용할 때 유용합니다.
    """
    return rd
