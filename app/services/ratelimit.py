import logging
import random
import time

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMRateLimiter:
    """Global fixed-window limiter shared by every worker process.

    Celery's own `rate_limit` is per worker instance, so it can't enforce a
    global budget. Fixed window = simple and cheap; the cost is up to 2x burst
    at a window boundary. Swap for a token bucket if that ever matters.

    Fails CLOSED: if Redis is unreachable we defer rather than risk blowing the
    provider quota / budget.
    """

    def __init__(
        self,
        client: Redis,
        limit: int | None = None,
        window_seconds: int | None = None,
    ):
        self._client = client
        self._limit = limit if limit is not None else settings.llm_rate_limit_per_minute
        self._window = window_seconds or settings.llm_rate_limit_window_seconds

    def acquire(self) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.time()
        key = f"rl:llm:{int(now // self._window)}"
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, self._window * 2)
            count, _ = pipe.execute()
        except RedisError:
            logger.warning("rate limiter unavailable, deferring", exc_info=True)
            return False, 30

        if count <= self._limit:
            return True, 0
        # Jitter so deferred tasks don't all wake at the exact window boundary.
        retry_after = int(self._window - (now % self._window)) + random.randint(1, 5)
        return False, retry_after
