class LLMError(Exception):
    pass


class LLMRetryableError(LLMError):
    """Timeouts, 5xx, overloaded, malformed output. Worth retrying with backoff."""


class LLMPermanentError(LLMError):
    """Bad credentials, invalid request, etc. Retrying will not help."""


class RateLimited(LLMError):
    """No LLM budget right now (our limiter or the provider's). Try again later."""

    def __init__(self, retry_after: int, message: str = "rate limited"):
        super().__init__(message)
        self.retry_after = retry_after
