from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Infrastructure
    database_url: str
    redis_broker_url: str
    redis_cache_url: str
    redis_ratelimit_url: str

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    ingest_api_key: str

    # LLM
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.5-flash"
    llm_timeout_seconds: float = 20.0
    llm_max_tokens: int = 1024
    llm_max_input_chars: int = 4000

    # Global (all workers) LLM call budget
    llm_rate_limit_per_minute: int = 30
    llm_rate_limit_window_seconds: int = 60

    # Classification cache
    classification_cache_ttl_seconds: int = 24 * 3600

    # Task behaviour
    llm_max_retries: int = 3                 # real failures (timeouts, 5xx, bad output)
    max_rate_limit_deferrals: int = 60       # waiting for rate-limit budget
    sweeper_pending_after_seconds: int = 300  # re-enqueue tickets stuck in "pending"
    fallback_team_name: str = "Triage"


settings = Settings()
