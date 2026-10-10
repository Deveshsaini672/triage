import logging

from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.classification import ClassificationResult
from app.services.llm import PROMPT_VERSION

logger = logging.getLogger(__name__)


class ClassificationCache:
    """Near-duplicate cache keyed by normalized-content hash.

    Fails open: a Redis problem means a cache miss, never a failed ticket.
    """

    def __init__(self, client: Redis, ttl: int | None = None):
        self._client = client
        self._ttl = ttl or settings.classification_cache_ttl_seconds

    @staticmethod
    def _key(content_hash: str) -> str:
        return f"classify:{PROMPT_VERSION}:{content_hash}"

    def get(self, content_hash: str) -> ClassificationResult | None:
        try:
            raw = self._client.get(self._key(content_hash))
            return ClassificationResult.model_validate_json(raw) if raw else None
        except (RedisError, ValidationError):
            logger.warning("classification cache read failed", exc_info=True)
            return None

    def set(self, content_hash: str, result: ClassificationResult) -> None:
        try:
            self._client.set(self._key(content_hash), result.model_dump_json(), ex=self._ttl)
        except RedisError:
            logger.warning("classification cache write failed", exc_info=True)
