import redis

from app.core.config import settings


def _client(url: str) -> redis.Redis:
    return redis.Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
    )


cache_client = _client(settings.redis_cache_url)
ratelimit_client = _client(settings.redis_ratelimit_url)
