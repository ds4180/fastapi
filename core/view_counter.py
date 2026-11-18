import logging
from typing import Optional
from fastapi import Request
from redis.exceptions import RedisError
from redis_config import rd
from models import User

logger = logging.getLogger("view_counter")

VIEW_COUNT_TTL_SECONDS = 86400  # 24시간


def _extract_viewer_id(request: Request, current_user: Optional[User]) -> str:
    if current_user and getattr(current_user, "id", None):
        return f"u:{current_user.id}"

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return f"ip:{ip}"

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return f"ip:{real_ip.strip()}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def should_count_view(
    resource_type: str,
    resource_key: str | int,
    request: Request,
    current_user: Optional[User] = None,
    ttl_seconds: int = VIEW_COUNT_TTL_SECONDS,
) -> bool:
    """
    Redis SET NX EX를 이용해 동일 사용자/IP의 24시간 내 중복 조회수 증가를 방지합니다.
    Redis 일시 장애 시에는 열람 흐름을 막지 않도록 True(Fail-Safe)를 반환합니다.
    """
    viewer_id = _extract_viewer_id(request, current_user)
    redis_key = f"view:{resource_type}:{resource_key}:{viewer_id}"
    try:
        return bool(rd.set(redis_key, "1", ex=ttl_seconds, nx=True))
    except RedisError as err:
        logger.warning(f"⚠️ [ViewCounter] Redis error, fallback to count=True: {err}")
        return True
