from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "pre-IPO"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/pre_ipo")

    sec_edgar_user_agent: str = Field(default="pre-ipo-research/1.0 (alexhavryleshko@gmail.com)")
    newsapi_api_key: str | None = None
    crunchbase_api_key: str | None = None
    fred_api_key: str | None = None
    twitter_bearer_token: str | None = None

    request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    source_cache_ttl_hours: int = Field(default=24, ge=1, le=168)

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return ["http://localhost:3000"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise TypeError("cors_origins must be a comma-separated string or list")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
