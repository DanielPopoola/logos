from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str

    llm_base_url: str
    llm_api_key: str
    llm_model_name: str
    llm_embedding_model_name: str

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
