import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(value: Any) -> list[str]:
    if value is None:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise TypeError("cors_origins JSON value must decode to a list")
            return [str(o).strip() for o in parsed if str(o).strip()]
        return [o.strip() for o in value.split(",") if o.strip()]
    if isinstance(value, list):
        return [str(o).strip() for o in value if str(o).strip()]
    raise TypeError("cors_origins must be a comma-separated string or list")


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
    llm_api_key: str | None = None
    llm_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    llm_base_url: str | None = "https://api.together.xyz/v1"

    request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    source_cache_ttl_hours: int = Field(default=24, ge=1, le=168)

    cors_origins: str | list[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001", "http://localhost:5173", "http://127.0.0.1:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        return _parse_cors_origins(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
