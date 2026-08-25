from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str

    llm_base_url: str
    llm_api_key: str
    llm_model_name: str
    llm_embedding_model_name: str
    llm_embedding_dimensions: int = 768

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Defaults to "production" so a missing/unset env var never accidentally
    # exposes test-only routes - opting into "test"/"development" must be
    # explicit.
    environment: str = "production"

    log_level: str = "INFO"
    sentry_dsn: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
